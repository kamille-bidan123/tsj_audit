#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trace Agent - 代码污点追踪审计 Agent

两阶段审计流程:
1. 探索阶段：多轮对话，使用 file_tool 和 tags_tool 探索代码
2. 输出阶段：根据探索信息生成 codemap

输出 trace_results = function_info + code_map
"""

import os
import sys
import json
import re
import importlib.util
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class CodeContext:
    """代码上下文信息"""
    function_name: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    is_entry_point: bool = False
    taint_source: Optional[str] = None
    taint_path: Optional[str] = None


@dataclass
class FunctionInfo:
    """回调函数信息（与 scan.py 输出兼容）"""
    func_name: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str
    project_type: str
    attack_surface: str


@dataclass
class ToolCall:
    """工具调用记录"""
    command: str
    args: str
    result: str
    logic: str = ""  # LLM 解释为什么要调用这个工具


@dataclass
class ExplorationSession:
    """探索会话记录"""
    function_info: FunctionInfo
    tool_calls: List[ToolCall] = field(default_factory=list)
    messages: List[Dict[str, str]] = field(default_factory=list)
    notes: str = ""  # LLM 的探索笔记


@dataclass
class TraceResult:
    """追踪结果"""
    function_info: FunctionInfo
    code_map: List[CodeContext]
    exploration: ExplorationSession


class TraceAgent:
    """
    污点追踪审计 Agent

    两阶段流程:
    1. 探索阶段：多轮对话 + 工具调用探索代码
    2. 输出阶段：生成 codemap
    """

    def __init__(
        self,
        project_type: str,
        attack_surface: str,
        project_path: str = ".",
        debug: bool = False,
    ):
        self.project_type = project_type
        self.attack_surface = attack_surface
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

    def load_input_knowledge(self) -> str:
        """加载外部输入知识"""
        input_path = Path(__file__).parent.parent / "knowledge" / self.project_type / self.attack_surface / "input.md"

        if not input_path.exists():
            if self.debug:
                print(f"[警告] 未找到输入知识文件：{input_path}", file=sys.stderr)
            return ""

        with open(input_path, "r", encoding="utf-8") as f:
            self._input_knowledge = f.read()

        if self.debug:
            print(f"[TraceAgent] 加载输入知识：{input_path}", file=sys.stderr)

        return self._input_knowledge

    def load_scan_results(self, code_path: Optional[str] = None) -> List[FunctionInfo]:
        """加载 scan.py 扫描结果"""
        if code_path is None:
            code_path = self.project_path

        scan_path = Path(__file__).parent.parent / "knowledge" / self.project_type / self.attack_surface / "scan.py"

        if not scan_path.exists():
            raise FileNotFoundError(f"未找到 scan.py: {scan_path}")

        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)

        if self.debug:
            print(f"[TraceAgent] 执行扫描：{scan_path} {code_path}", file=sys.stderr)

        results = scan_module.scan_directory(code_path)
        self._scan_results = results
        return results

    def call_tool(self, command: str) -> str:
        """
        调用工具执行命令

        Args:
            command: 工具命令，如 "read_file main.c:1-20"

        Returns:
            执行结果
        """
        from tools.executor import ToolExecutor
        result = ToolExecutor.call(command)
        if self.debug:
            print(f"  [Tool] {command} -> {result}...", file=sys.stderr)
        return result

    def _build_exploration_system_prompt(self) -> str:
        """构建探索阶段系统提示"""
        input_knowledge = self._input_knowledge or self.load_input_knowledge()

        return f"""你是一个代码安全审计专家，专门进行污点分析 (taint analysis)。

## 任务
你的任务是从接口函数开始，探索代码中的外部输入污染路径。

## 输入知识
{input_knowledge}

## 可用工具
你可以使用以下工具来探索代码：

### 文件工具
- `read_file <path>[:<start>-<end>]` - 读取文件内容，可指定行范围
  示例：`read_file main.c:1-50`
- `list_dir [path]` - 列出目录内容
  示例：`list_dir src/`
- `search_code <pattern> [path]` - 搜索代码关键字
  示例：`search_code "sprintf" .`

### 代码导航工具
- `go_to_def <symbol>` - 跳转到符号定义处
  示例：`go_to_def handle_request`
- `find_refs <symbol>` - 查找符号的所有引用
  示例：`find_refs user_input`
- `list_symbols [pattern]` - 列出符号
  示例：`list_symbols handler`

## 输出格式
每轮对话，你需要返回 JSON 格式（每轮只能调用一个工具）：
```json
{{
    "command": "read_file main.c:1-50",
    "logic": "查看主处理函数"
}}
```

或者使用 submit 命令结束探索阶段：
```json
{{
    "command": "submit",
    "logic": "探索完成，已发现所有污染路径"
}}
```

## 审计目标
1. 识别外部输入点 (mg_get_var, mg_read, mg_get_header 等)
2. 追踪数据如何传递给其他函数
3. 识别危险函数 (system, sprintf, strcpy, fopen 等)
4. 构建完整的污染调用链

请仔细探索代码，记录你的发现。"""

    def _build_exploration_user_message(self, func_info: FunctionInfo) -> str:
        """构建探索阶段用户消息"""
        return f"""请从以下接口函数开始探索：

函数名：{func_info.func_name}
文件：{func_info.file_path}
行号：{func_info.start_line}-{func_info.end_line}

代码片段:
{func_info.code_snippet}

请使用工具调用来探索这个函数是否存在外部输入污染，追踪所有被污染的数据流。
当你认为已经探索完成时，使用 submit 命令结束探索阶段。"""

    def _parse_tool_calls_response(self, response: str) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        解析 LLM 响应，提取工具调用

        Returns:
            (is_submit, command, args, logic)
        """
        is_submit = False
        command = None
        args = None
        logic = ""

        # 查找 JSON
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, response, re.DOTALL)

        json_str = ""
        if matches:
            json_str = matches[0]
        else:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)

        if json_str:
            try:
                data = json.loads(json_str)
                cmd = data.get("command", "")
                logic = data.get("logic", "")

                # 检查是否是 submit 命令
                if cmd == "submit":
                    is_submit = True
                else:
                    command = cmd
                    # 如果 command 包含空格，分离命令和参数
                    if " " in cmd:
                        parts = cmd.split(" ", 1)
                        command = parts[0]
                        args = parts[1] if len(parts) > 1 else ""
                    else:
                        args = data.get("args", "")
            except json.JSONDecodeError as e:
                if self.debug:
                    print(f"[警告] JSON 解析失败：{e}", file=sys.stderr)

        return is_submit, command, args, logic

    def explore_function(
        self,
        func_info: FunctionInfo,
        max_turns: int = 10,
    ) -> ExplorationSession:
        """
        第一阶段：探索阶段 - 多轮对话探索代码

        Args:
            func_info: 接口函数信息
            max_turns: 最大对话轮数

        Returns:
            ExplorationSession 探索会话记录
        """
        session = ExplorationSession(function_info=func_info)

        # 构建消息
        system_prompt = self._build_exploration_system_prompt()
        user_message = self._build_exploration_user_message(func_info)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        session.messages.append({"role": "system", "content": system_prompt})
        session.messages.append({"role": "user", "content": user_message})

        if self.debug:
            print(f"\n[探索阶段] 开始分析：{func_info.func_name}", file=sys.stderr)

        for turn in range(max_turns):
            if self.debug:
                print(f"\n[第{turn+1}轮]", file=sys.stderr)

            # 调用 LLM
            response = self.llm_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.1,
            )


            # 解析响应
            is_submit, command, args, logic = self._parse_tool_calls_response(response.content)

            # 检查是否提交
            if is_submit:
                session.notes = logic
                if self.debug:
                    print("[提交探索]", file=sys.stderr)
                break

            # 执行工具调用
            if not command:
                # 没有工具调用，可能是普通对话
                messages.append({"role": "assistant", "content": response.content})
                continue

            # 构建完整命令并执行
            full_command = f"{command} {args}".strip() if args else command
            result = self.call_tool(full_command)

            # 记录工具调用
            tool_call = ToolCall(
                command=command,
                args=args or "",
                result=result,
                logic=logic,
            )
            session.tool_calls.append(tool_call)

            # 将工具结果添加到对话
            messages.append({
                "role": "assistant",
                "content": f"调用工具：{full_command}\n目的：{logic}"
            })
            messages.append({
                "role": "user",
                "content": f"工具返回:\n{result}"
            })

        return session

    def _build_output_system_prompt(self) -> str:
        """构建输出阶段系统提示"""
        return """你是一个代码安全审计专家，负责生成污点分析报告。

## 任务
根据探索阶段的发现，生成完整的 codemap。

## 输出格式
输出 JSON 格式的 codemap 数组：
```json
[
    {
        "function_name": "函数名",
        "file_path": "文件路径",
        "line_start": 起始行号，
        "line_end": 结束行号，
        "code_snippet": "代码片段",
        "is_entry_point": true/false,
        "taint_source": "污染来源",
        "taint_path": "污染路径描述"
    }
]
```

## 要求
1. 从入口函数开始，列出所有被污染的函数
2. 标明每个函数的污染来源和污染路径
3. code_snippet 包含函数定义代码
4. 确保调用链完整"""

    def _build_output_user_message(self, session: ExplorationSession) -> str:
        """构建输出阶段用户消息"""
        func_info = session.function_info

        # 整理探索信息
        tool_results = []
        for tc in session.tool_calls:
            tool_results.append(f"- {tc.command} {tc.args}: {tc.result[:200]}")

        tool_results_str = "\n".join(tool_results) if tool_results else "无"

        return f"""入口函数:
- 函数名：{func_info.func_name}
- 文件：{func_info.file_path}:{func_info.start_line}-{func_info.end_line}
- 代码:
{func_info.code_snippet}

探索记录:
工具调用 ({len(session.tool_calls)} 次):
{tool_results_str}

探索笔记:
{session.notes}

请根据以上探索信息，生成完整的 codemap，包含所有被污染的函数调用链。"""

    def _parse_codemap_response(self, response: str, entry_func: FunctionInfo) -> List[CodeContext]:
        """解析 LLM 响应，提取 codemap"""
        codemap = []

        # 查找 JSON
        json_pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(json_pattern, response, re.DOTALL)

        json_str = ""
        if matches:
            json_str = matches[0]
        else:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group(0)

        if json_str:
            try:
                data = json.loads(json_str)
                for item in data:
                    ctx = CodeContext(
                        function_name=item.get("function_name", ""),
                        file_path=item.get("file_path", ""),
                        line_start=item.get("line_start", 1),
                        line_end=item.get("line_end", 1),
                        code_snippet=item.get("code_snippet", ""),
                        is_entry_point=item.get("is_entry_point", False),
                        taint_source=item.get("taint_source"),
                        taint_path=item.get("taint_path"),
                    )
                    codemap.append(ctx)
            except json.JSONDecodeError as e:
                if self.debug:
                    print(f"[警告] JSON 解析失败：{e}", file=sys.stderr)

        return codemap

    def generate_codemap(
        self,
        session: ExplorationSession,
    ) -> List[CodeContext]:
        """
        第二阶段：输出阶段 - 根据探索信息生成 codemap

        Args:
            session: 探索会话记录

        Returns:
            codemap 列表
        """
        if self.debug:
            print("\n[输出阶段] 生成 codemap...", file=sys.stderr)

        # 构建消息
        system_prompt = self._build_output_system_prompt()
        user_message = self._build_output_user_message(session)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # 调用 LLM
        response = self.llm_client.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.1,
        )


        # 解析响应
        codemap = self._parse_codemap_response(response.content, session.function_info)

        return codemap

    def audit_function(
        self,
        func_info: FunctionInfo,
        max_turns: int = 10,
    ) -> TraceResult:
        """
        完整审计单个函数

        Args:
            func_info: 接口函数信息
            max_turns: 探索阶段最大轮数

        Returns:
            TraceResult 追踪结果
        """
        # 第一阶段：探索
        exploration = self.explore_function(func_info, max_turns)

        # 第二阶段：输出
        code_map = self.generate_codemap(exploration)

        # 构建结果
        result = TraceResult(
            function_info=func_info,
            code_map=code_map,
            exploration=exploration,
        )

        return result

    def audit_all(
        self,
        code_path: Optional[str] = None,
        max_turns: int = 10,
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
        scan_results = self.load_scan_results(code_path)

        if self.debug:
            print(f"\n[TraceAgent] 找到 {len(scan_results)} 个接口函数", file=sys.stderr)

        # 加载输入知识
        self.load_input_knowledge()

        # 逐个审计
        trace_results = []

        for func_info in scan_results:
            if self.debug:
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"[TraceAgent] 审计函数：{func_info.func_name} @ {func_info.file_path}:{func_info.start_line}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)

            result = self.audit_function(func_info, max_turns)
            trace_results.append(result)

        return trace_results

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
            format: 输出格式 (json/text)

        Returns:
            输出文件路径
        """
        if format == "json":
            data = []
            for r in results:
                item = {
                    "function_info": asdict(r.function_info),
                    "code_map": [asdict(ctx) for ctx in r.code_map],
                    "exploration": {
                        "tool_calls": [asdict(tc) for tc in r.exploration.tool_calls],
                        "notes": r.exploration.notes,
                        "message_count": len(r.exploration.messages),
                    },
                }
                data.append(item)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        else:
            # 文本格式
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("Code Audit Trace Report\n")
                f.write("=" * 80 + "\n\n")

                for r in results:
                    f.write(f"\n# {r.function_info.func_name}\n\n")
                    f.write(f"文件：{r.function_info.file_path}:{r.function_info.start_line}-{r.function_info.end_line}\n\n")

                    f.write("## Code Map\n\n")
                    for i, ctx in enumerate(r.code_map, 1):
                        f.write(f"### {i}. {ctx.function_name}\n")
                        f.write(f"文件：{ctx.file_path}:{ctx.line_start}-{ctx.line_end}\n")
                        if ctx.is_entry_point:
                            f.write("**入口函数**\n")
                        if ctx.taint_source:
                            f.write(f"污染来源：{ctx.taint_source}\n")
                        if ctx.taint_path:
                            f.write(f"污染路径：{ctx.taint_path}\n")
                        f.write("\n```c\n")
                        f.write(ctx.code_snippet)
                        f.write("\n```\n\n")

                    f.write("## 探索记录\n\n")
                    f.write(f"工具调用次数：{len(r.exploration.tool_calls)}\n")
                    f.write(f"对话轮数：{len(r.exploration.messages)}\n\n")

                    if r.exploration.tool_calls:
                        f.write("工具调用:\n")
                        for tc in r.exploration.tool_calls:
                            f.write(f"  - {tc.command} {tc.args}\n")
                            f.write(f"    目的：{tc.logic}\n")
                            f.write(f"    结果：{tc.result[:100]}...\n")
                        f.write("\n")

                    if r.exploration.notes:
                        f.write(f"探索笔记:\n{r.exploration.notes}\n\n")

                    f.write("-" * 80 + "\n")

        if self.debug:
            print(f"\n[TraceAgent] 导出结果到：{output_path}", file=sys.stderr)

        return output_path


def create_trace_agent(
    project_type: str,
    attack_surface: str,
    project_path: str = ".",
    debug: bool = False,
) -> TraceAgent:
    """创建 TraceAgent 实例"""
    return TraceAgent(
        project_type=project_type,
        attack_surface=attack_surface,
        project_path=project_path,
        debug=debug,
    )
