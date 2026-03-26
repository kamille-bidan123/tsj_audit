#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trace Agent - 代码污点追踪审计 Agent

探索阶段：多轮对话，使用工具探索代码，最后输出 codemap
"""

import os
import sys
import json
import importlib.util
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from cli import get_config_object
import glob
import utils.export_utils
# 导入共享模型
from models import FunctionInfo, CodeContext, TraceResult, AuditResult
from utils.export_utils import merge_checkpoints_and_export


class SubmitTool:
    """提交探索结果的工具"""

    name = "submit"
    description = "探索工具"

    commands = {
        "submit": {
            "description": "探索完成，提交探索结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "探索发现的总结",
                    },
                },
                "required": ["summary"],
            },
        },
    }

    def execute(self, command: str, args: dict) -> str:
        return "已提交"


# 注册 submit 工具
ToolRegistry._commands["submit"] = SubmitTool
ToolRegistry._tools["submit"] = SubmitTool


class TraceAgent:
    """
    污点追踪审计 Agent

    探索阶段：多轮对话 + 工具调用探索代码，最后输出 codemap
    审计阶段：基于 codemap 调用 sub-agent 进行漏洞审计
    """

    # 探索阶段使用的工具
    EXPLORATION_TOOLS = [
        "read_file", "list_dir", "search_code",
        "go_to_def", "find_refs",
        "skill",  # Skills 工具
        "submit",
    ]

    # 审计阶段使用的工具（sub-agent 调用）
    AUDIT_TOOLS = [
        "submit",
    ]

    def __init__(
        self,
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
    ):
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

        self._llm_client = None
        self._input_knowledge: Optional[str] = None
        self._scan_results: Optional[List[FunctionInfo]] = None

    def _get_checkpoint_dir(self, output_dir: str) -> Path:
        """获取中间信息保存目录"""
        return Path(output_dir) / "checkpoints"

    def _get_checkpoint_file(self, output_dir: str, func_name: str) -> Path:
        """获取单个函数的检查点文件路径"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)
        # 清理函数名中的非法字符
        safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in func_name)
        return checkpoint_dir / f"{safe_name}.json"

    def _save_checkpoint(self, output_dir: str, result: TraceResult):
        """保存审计检查点"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_file = self._get_checkpoint_file(output_dir, result.function_info.func_name)
        data = result.model_dump()

        # 添加元信息
        data["_checkpoint_meta"] = {
            "saved_at": datetime.now().isoformat(),
            "func_name": result.function_info.func_name,
            "file_path": result.function_info.file_path,
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [检查点] 已保存: {checkpoint_file}", file=sys.stderr)

    def _save_conversation_history(self, agent_name: str, func_info: FunctionInfo, messages: List[Dict]):
        """保存特定 agent 的对话历史"""
        if not hasattr(self, 'output_dir') or not self.output_dir:
            return  # 如果没有设置输出目录，则不保存

        # 构建输出目录结构：output_dir/conversations/agent_name/function_name.json
        conversations_dir = Path(self.output_dir) / "conversations" / agent_name
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # 清理函数名中的非法字符
        safe_func_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in func_info.func_name)

        conversation_file = conversations_dir / f"{safe_func_name}.json"

        # 准备保存对话历史
        conversation_data = {
            "function_info": func_info.model_dump(),
            "conversation_history": messages,
            "saved_at": datetime.now().isoformat(),
            "agent": agent_name
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [对话历史] {agent_name} 已保存: {conversation_file}", file=sys.stderr)

    def _load_checkpoint(self, output_dir: str, func_name: str) -> Optional[TraceResult]:
        """加载单个函数的审计检查点"""
        checkpoint_file = self._get_checkpoint_file(output_dir, func_name)

        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 移除元信息
            data.pop("_checkpoint_meta", None)

            result = TraceResult.model_validate(data)
            return result
        except Exception as e:
            if self.debug:
                print(f"  [警告] 加载检查点失败: {e}", file=sys.stderr)
            return None

    def _load_all_checkpoints(self, output_dir: str) -> Dict[str, TraceResult]:
        """加载所有审计检查点"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)

        if not checkpoint_dir.exists():
            return {}

        checkpoints = {}
        for checkpoint_file in checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                meta = data.pop("_checkpoint_meta", None)
                if meta:
                    func_name = meta.get("func_name", checkpoint_file.stem)
                    checkpoints[func_name] = TraceResult.model_validate(data)
            except Exception as e:
                if self.debug:
                    print(f"  [警告] 加载检查点失败 ({checkpoint_file}): {e}", file=sys.stderr)

        return checkpoints

    @property
    def llm_client(self):
        """懒加载 LLM 客户端"""
        if self._llm_client is None:
            from utils.llm_client import LLMClient
            self._llm_client = LLMClient()
        return self._llm_client


    def load_scan_results(self, scan_path: str, code_path: Optional[str] = None) -> List[FunctionInfo]:
        """加载 JSON 文件扫描结果"""
        if code_path is None:
            code_path = self.project_path

        scan_path = Path(scan_path)

        if not scan_path.exists():
            raise FileNotFoundError(f"未找到扫描结果文件: {scan_path}")

        # 检查是否是 JSON 文件
        if scan_path.suffix.lower() == '.json':
            # 读取 JSON 文件
            with open(scan_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            # 验证数据结构是否为 FunctionInfo 的列表
            if not isinstance(raw_data, list):
                raise ValueError(f"JSON 文件内容不是列表格式: {scan_path}")

            results = []
            for idx, item in enumerate(raw_data):
                if isinstance(item, dict):
                    # 验证字典是否符合 FunctionInfo 结构
                    try:
                        function_info = FunctionInfo(**item)
                        results.append(function_info)
                    except Exception as e:
                        raise ValueError(f"JSON 文件中第 {idx+1} 项不是有效的 FunctionInfo 结构: {str(e)}")
                elif isinstance(item, FunctionInfo):
                    # 已经是 FunctionInfo 对象
                    results.append(item)
                else:
                    raise ValueError(f"JSON 文件中第 {idx+1} 项既不是字典也不是 FunctionInfo 对象")
        else:
            # 兼容旧的 Python 模块方式（如果需要的话）
            if not scan_path.exists():
                raise FileNotFoundError(f"未找到 scan.py: {scan_path}")

            spec = importlib.util.spec_from_file_location("scan_module", scan_path)
            scan_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scan_module)

            if self.debug:
                print(
                    f"[TraceAgent] 执行扫描：{scan_path} {code_path}", file=sys.stderr)

            raw_results = scan_module.scan_directory(code_path)

            # 将字典转换为 FunctionInfo 对象
            results = []
            for item in raw_results:
                if isinstance(item, dict):
                    # 字典转 FunctionInfo
                    results.append(FunctionInfo(**item))
                else:
                    # 已经是 FunctionInfo 对象
                    results.append(item)

        self._scan_results = results
        return results

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """调用工具执行"""
        result = ToolExecutor.call(name, arguments)
        if self.debug:
            print(f"  [Tool] {name}({arguments}) -> {result[:100]}...", file=sys.stderr)
        return result

    def _build_exploration_system_prompt(self) -> str:
        """构建探索阶段系统提示"""

        return f"""你是一个代码安全审计专家，专门进行污点分析 (taint analysis)。

## 任务
你的任务是从接口函数开始，探索代码中的外部输入污染路径。


## 审计目标
1. 识别外部输入点 (mg_get_var, mg_read, mg_get_header 等)
2. 追踪数据如何传递给其他函数
3. 识别危险函数 (system, sprintf, strcpy, fopen 等)
4. 构建完整的污染调用链

## 工具使用
你可以使用提供的工具来探索代码。每次调用一个工具，根据结果决定下一步行动。
工具的详细说明（包括参数和使用场景）已在工具 schema 中定义，请参考工具描述。

## Output Format (Output Format)
当你认为已经探索完成时，调用 submit 工具提交你的发现总结。
"""

    def _build_exploration_user_message(self, func_info: FunctionInfo) -> str:
        """构建探索阶段用户消息"""
        return f"""请从以下接口函数开始探索：

函数名：{func_info.func_name}
文件：{func_info.file_path}
行号：{func_info.start_line}-{func_info.end_line}

代码片段:
{func_info.code_snippet}

## 外部输入知识
{func_info.input}

请使用工具调用来探索这个函数是否存在外部输入污染，追踪所有被污染的数据流。
当你认为已经探索完成时，调用 submit 工具提交你的发现总结。
强制要求：
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
重要的事情说三遍


"""

    def audit_function(
        self,
        func_info: FunctionInfo,
    ) -> TraceResult:
        """
        审计单个函数

        Args:
            func_info: 接口函数信息
            max_turns: 探索阶段最大轮数

        Returns:
            TraceResult 追踪结果
        """
        # 构建消息
        system_prompt = self._build_exploration_system_prompt()
        user_message = self._build_exploration_user_message(func_info)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if self.debug:
            print(f"\n[探索阶段] 开始分析：{func_info.func_name}", file=sys.stderr)

        max_turns = get_config_object().max_turns
        for turn in range(max_turns):
            if self.debug:
                print(f"\n[第{turn+1}轮]", file=sys.stderr)

            # 调用 LLM with tools
            # if self.debug:
            #     import json
            #     print(f"\n[DEBUG] messages: {json.dumps(messages[-2:] if len(messages) > 2 else messages, ensure_ascii=False, indent=2)}", file=sys.stderr)

            response = self.llm_client.chat(
                messages=messages,
                tools=ToolRegistry.to_openai_tools(self.EXPLORATION_TOOLS),
                tool_choice="required",  # 强制必须调用工具
                temperature=0.1,
            )

            # 检查是否有工具调用
            if response.tool_calls:
                for tc in response.tool_calls:
                    print(f"\n[工具调用] {tc['function']['name']}({tc['function']['arguments']})", file=sys.stderr)
                    func_name = tc["function"]["name"]
                    arguments = tc["function"]["arguments"]

                    # 检查是否是 submit 调用
                    if func_name == "submit":
                        if self.debug:
                            print("[提交探索]", file=sys.stderr)
                        # 进入 codemap 生成阶段
                        return self._generate_codemap(func_info, messages)

                    # 执行工具
                    result = self.call_tool(func_name, arguments)

                    # 将工具结果添加到对话
                    # 注意：arguments 需要转回 JSON 字符串
                    tc_for_message = {
                        "id": tc["id"],
                        "type": tc["type"],
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False),
                        }
                    }
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tc_for_message],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
            else:
                print("在tool_choice=required模式下，未检测到工具调用", file=sys.stderr)
                messages.append({
                    "role": "user",
                    "content": "请使用工具进行探索，或调用 submit 工具结束探索。"
                })

        # 达到最大轮数，生成 codemap
        return self._generate_codemap(func_info, messages)

    def _generate_codemap(
        self,
        func_info: FunctionInfo,
        messages: List[Dict],
    ) -> TraceResult:
        """生成 codemap"""
        if self.debug:
            print("\n[输出阶段] 生成 codemap...", file=sys.stderr)

        # 添加 codemap 生成请求
        messages.append({
            "role": "user",
            "content": f"""请根据以上探索信息，生成完整的 codemap，包含所有被污染的函数调用链，并描述函数的主要业务逻辑。

入口函数：{func_info.func_name}
文件：{func_info.file_path}:{func_info.start_line}-{func_info.end_line}

输出格式要求（JSON对象）：
{{
  "code_logic": "函数的业务逻辑描述",
  "code_map": [
    {{
      "function_name": "函数名",
      "file_path": "文件路径",
      "line_start": 起始行号,
      "line_end": 结束行号,
      "code_snippet": "代码片段",
      "is_entry_point": true/false,
      "taint_source": "污染源（可选）",
      "taint_path": "污染路径（可选）"
    }}
  ]
}}
"""
        })

        # 使用 JSON 输出格式
        response = self.llm_client.chat(
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        # 解析 codemap
        try:
            # 使用 extract_json 提取 JSON（处理 markdown 代码块）
            from utils.llm_client import extract_json
            json_str = extract_json(response.content)
            if not json_str:
                # 尝试重试一次，强制要求只输出 JSON
                print("[重试] 强制要求 JSON 输出...", file=sys.stderr)
                messages.append({
                    "role": "user",
                    "content": "请只输出 JSON 格式的 codemap，不要输出任何其他文字。直接输出 JSON 对象："
                })
                response = self.llm_client.chat(
                    messages=messages,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                json_str = extract_json(response.content)

            if not json_str:
                raise ValueError("未找到有效的 JSON 内容")
            data = json.loads(json_str)
            code_logic = data.get("code_logic", "")
            items = data.get("code_map", [])
            code_map = [CodeContext.model_validate(item) for item in items]
        except (json.JSONDecodeError, Exception) as e:
            if self.debug:
                print(f"[警告] codemap 解析失败：{e}", file=sys.stderr)
                if response.content:
                    print(f"[响应内容] {response.content[:200]}...", file=sys.stderr)
            code_map = []
            code_logic = ""

        # 将 codemap 响应添加到消息
        messages.append({
            "role": "assistant",
            "content": response.content,
        })

        # 直接进入审计阶段，不需要额外的消息
        if self.debug:
            print(f"\n[审计阶段] 启动 AuditAgent 运行所有审计类型", file=sys.stderr)

        # 调用 AuditAgent 进行审计（自动运行所有审计类型）
        from agents.audit_agent import AuditAgent
        audit_agent = AuditAgent(
            function_info=func_info,
            code_map=code_map,
            project_path=self.project_path,
            debug=self.debug,
            output_dir=self.output_dir,
        )

        audit_results, exploit_results = audit_agent.audit()

        if self.debug:
            print(f"  [审计结果] 总计发现 {len(audit_results)} 个潜在漏洞", file=sys.stderr)
            for ar in audit_results:
                print(f"    - {ar.vulnerability_type}: {ar.is_vulnerable} (置信度: {ar.confidence})", file=sys.stderr)

        # 保存 trace agent 的对话历史
        self._save_conversation_history("trace_agent", func_info, messages)

        return TraceResult(
            function_info=func_info,
            code_logic=code_logic,
            code_map=code_map,
            audit_results=audit_results,
            exploit_results=exploit_results,
        )

    def audit_all(
        self,
        scan_path,
        code_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        resume: bool = False,
    ) -> None:
        """
        审计所有接口函数

        Args:
            code_path: 代码目录路径
            output_dir: 输出目录路径，用于保存中间检查点
            resume: 是否从中间断点恢复审计

        说明:
            审计结果会逐个保存到 output_dir/checkpoints/ 目录，
            完成后会自动合并所有 checkpoint 生成最终报告。
        """
        # 设置输出目录，以便后续保存对话历史
        self.output_dir = output_dir

        # 加载扫描结果
        scan_results = self.load_scan_results(scan_path, code_path)

        if self.debug:
            print(
                f"\n[TraceAgent] 找到 {len(scan_results)} 个接口函数", file=sys.stderr)

        # 如果启用了resume模式，加载已有的检查点
        checkpoints = {}
        completed_funcs = set()
        if resume and output_dir:
            checkpoints = self._load_all_checkpoints(output_dir)
            completed_funcs = set(checkpoints.keys())
            if self.debug and completed_funcs:
                print(f"\n[TraceAgent] 从检查点恢复: 找到 {len(completed_funcs)} 个已完成的函数", file=sys.stderr)

        # 逐个审计
        for func_info in scan_results:
            func_name = func_info.func_name

            # 检查是否已完成
            if func_name in completed_funcs:
                if self.debug:
                    print(f"\n[跳过] {func_name} (已完成，来自检查点)", file=sys.stderr)
                continue

            # 新审计未完成的函数
            if self.debug:
                print(f"\n{'='*60}", file=sys.stderr)
                print(
                    f"[TraceAgent] 审计函数：{func_name} @ {func_info.file_path}:{func_info.start_line}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)

            result = self.audit_function(func_info)

            # 保存检查点
            if output_dir:
                self._save_checkpoint(output_dir, result)

        # 合并所有 checkpoint 生成最终报告
        if output_dir:
            merge_checkpoints_and_export(output_dir, debug=self.debug)

    def audit_single(
        self,
        func_info,
    ) -> 'TraceResult':
        """
        审计单个函数

        Args:
            func_info: 接口函数信息

        Returns:
            TraceResult 追踪结果
        """
        return self.audit_function(func_info)


