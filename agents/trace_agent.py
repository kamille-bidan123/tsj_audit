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
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from cli import get_config_object

# 导入共享模型
from models import FunctionInfo, CodeContext, TraceResult, AuditResult


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
        "go_to_def", "find_refs", "list_symbols",
        "skill",  # Skills 工具
        "submit",
    ]

    # 审计阶段使用的工具（sub-agent 调用）
    AUDIT_TOOLS = [
        "audit",
        "submit",
    ]

    def __init__(
        self,
        project_path: str = ".",
        debug: bool = False,
    ):
        self.project_path = project_path
        self.debug = debug

        self._llm_client = None
        self._input_knowledge: Optional[str] = None
        self._scan_results: Optional[List[FunctionInfo]] = None

    @property
    def llm_client(self):
        """懒加载 LLM 客户端"""
        if self._llm_client is None:
            from utils.llm_client import LLMClient
            self._llm_client = LLMClient()
        return self._llm_client


    def load_scan_results(self, scan_path: str,code_path: Optional[str] = None) -> List[FunctionInfo]:
        """加载 scan.py 扫描结果"""
        if code_path is None:
            code_path = self.project_path

        scan_path = Path(scan_path)

        if not scan_path.exists():
            raise FileNotFoundError(f"未找到 scan.py: {scan_path}")

        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)

        if self.debug:
            print(
                f"[TraceAgent] 执行扫描：{scan_path} {code_path}", file=sys.stderr)

        results = scan_module.scan_directory(code_path)
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
                        "content": None,
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
            "content": f"""请根据以上探索信息，生成完整的 codemap，包含所有被污染的函数调用链。

入口函数：{func_info.func_name}
文件：{func_info.file_path}:{func_info.start_line}-{func_info.end_line}

输出格式要求（JSON对象）：
{{
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
            items = data.get("code_map", [])
            code_map = [CodeContext.model_validate(item) for item in items]
        except (json.JSONDecodeError, Exception) as e:
            if self.debug:
                print(f"[警告] codemap 解析失败：{e}", file=sys.stderr)
                if response.content:
                    print(f"[响应内容] {response.content[:200]}...", file=sys.stderr)
            code_map = []

        # 将 codemap 响应添加到消息
        messages.append({
            "role": "assistant",
            "content": response.content,
        })

        # 审计阶段：追加提示词，切换工具集
        messages.append({
            "role": "user",
            "content": """基于以上 codemap，请选择合适的审计类型进行分析：
- command_injection: 命令注入漏洞审计（如 system、popen 等）
- path_traversal: 路径遍历漏洞审计（如 fopen、open 等）

调用 audit 工具启动相应的审计 Agent。审计完成后调用 submit 结束。"""
        })

        # 单轮审计调用
        audit_results = []
        exploit_results = []
        response = self.llm_client.chat(
            messages=messages,
            tools=ToolRegistry.to_openai_tools(self.AUDIT_TOOLS),
            tool_choice="auto",
            temperature=0.1,
        )

        if response.tool_calls:
            for tc in response.tool_calls:
                print(f"\n[审计工具调用] {tc['function']['name']}({tc['function']['arguments']})", file=sys.stderr)
                func_name = tc["function"]["name"]

                if func_name == "audit":
                    if self.debug:
                        print(f"\n[审计阶段] 启动 AuditAgent", file=sys.stderr)

                    # 获取审计类型参数
                    audit_type = tc["function"]["arguments"].get("audit_type", "command_injection")

                    if self.debug:
                        print(f"  [类型] {audit_type}", file=sys.stderr)

                    # 调用 AuditAgent 进行审计
                    from agents.audit_agent import AuditAgent
                    audit_agent = AuditAgent(
                        audit_type=audit_type,
                        function_info=func_info,
                        code_map=code_map,
                        project_path=self.project_path,
                        debug=self.debug,
                    )

                    audit_result, exploit_result = audit_agent.audit()

                    if audit_result:
                        audit_results.append(audit_result)
                        if self.debug:
                            print(f"  [审计结果] 漏洞: {audit_result.is_vulnerable}, 置信度: {audit_result.confidence}", file=sys.stderr)

                    if exploit_result:
                        exploit_results.append(exploit_result)
                        if self.debug:
                            print(f"  [利用结果] 成功: {exploit_result.success}", file=sys.stderr)

        return TraceResult(
            function_info=func_info,
            code_map=code_map,
            audit_results=audit_results,
            exploit_results=exploit_results,
        )

    def audit_all(
        self,
        scan_path,
        code_path: Optional[str] = None,
    ) -> List[TraceResult]:
        """
        审计所有接口函数

        Args:
            code_path: 代码目录路径
            max_turns: 每个函数探索最大轮数

        Returns:
            TraceResult 列表
        """
        # 加载扫描结果
        scan_results = self.load_scan_results(scan_path, code_path)

        if self.debug:
            print(
                f"\n[TraceAgent] 找到 {len(scan_results)} 个接口函数", file=sys.stderr)


        # 逐个审计
        trace_results = []

        for func_info in scan_results:
            if self.debug:
                print(f"\n{'='*60}", file=sys.stderr)
                print(
                    f"[TraceAgent] 审计函数：{func_info.func_name} @ {func_info.file_path}:{func_info.start_line}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)

            result = self.audit_function(func_info)
            trace_results.append(result)

        return trace_results

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

    def export_results(
        self,
        results: List[TraceResult],
        output_path: str,
        format: str = "json",
    ) -> str:
        """
        导出审计结果

        Args:
            results: TraceResult 列表
            output_path: 输出路径
            format: 输出格式 ("json" 或 "html")

        Returns:
            输出文件路径
        """
        from utils.export_utils import export_results as export
        return export(results, output_path, format)