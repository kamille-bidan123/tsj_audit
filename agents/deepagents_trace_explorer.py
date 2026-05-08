#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepAgents-backed trace exploration and codemap generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError

from agents.prompt import EXPLORATION_SYSTEM_PROMPT, build_exploration_user_message
from models import CodeContext, FunctionInfo
from tools.executor import ToolExecutor
from utils.deepagents_runtime import (
    GraphRecursionError,
    build_deepagents_invoke_config,
    recursion_limit_message,
)
from utils.deepagents_output import extract_structured_model
from utils.tool_call_guard import ToolCallGuard


class DeepTraceOutput(BaseModel):
    """Structured output expected from the DeepAgents trace explorer."""

    code_logic: str = Field(description="函数的业务逻辑描述")
    code_map: List[CodeContext] = Field(description="所有被污染的函数调用链上下文")


def _call_tool(
    command: str,
    arguments: Dict[str, Any],
    *,
    audit_function_name: str | None = None,
    tool_guard: ToolCallGuard | None = None,
) -> str:
    return ToolExecutor.call(
        command,
        arguments,
        audit_function_name=audit_function_name,
        tool_guard=tool_guard,
    )


def project_go_to_def(symbol: str) -> str:
    """Find definitions for a symbol using the project code index."""
    return _call_tool("go_to_def", {"symbol": symbol})


def project_find_refs(symbol: str) -> str:
    """Find references for a symbol using the project code index."""
    return _call_tool("find_refs", {"symbol": symbol})


def project_skill(name: str) -> str:
    """Load a project skill document by name."""
    return _call_tool("skill", {"name": name})


def make_project_tools(
    audit_function_name: str | None = None,
    *,
    tool_guard: ToolCallGuard | None = None,
) -> list:
    """Create project navigation tools bound to the current audited function."""

    def project_go_to_def(symbol: str) -> str:
        """Find definitions for a symbol using the project code index."""
        return _call_tool(
            "go_to_def",
            {"symbol": symbol},
            audit_function_name=audit_function_name,
            tool_guard=tool_guard,
        )

    def project_find_refs(symbol: str) -> str:
        """Find references for a symbol using the project code index."""
        return _call_tool(
            "find_refs",
            {"symbol": symbol},
            audit_function_name=audit_function_name,
            tool_guard=tool_guard,
        )

    def project_skill(name: str) -> str:
        """Load a project skill document by name."""
        return _call_tool(
            "skill",
            {"name": name},
            audit_function_name=audit_function_name,
            tool_guard=tool_guard,
        )

    return [project_go_to_def, project_find_refs, project_skill]


class DeepAgentsTraceExplorer:
    """Run trace exploration with DeepAgents inside the outer LangGraph workflow."""

    TOOLS = [
        project_go_to_def,
        project_find_refs,
        project_skill,
    ]

    def __init__(self, trace_agent):
        self.trace_agent = trace_agent
        self._agent = None
        self._tool_guard = None
        self.audit_function_name: str | None = None

    def run(self, func_info: FunctionInfo) -> tuple[str, List[CodeContext], List[Dict[str, Any]]]:
        self.audit_function_name = func_info.func_name
        user_message = build_exploration_user_message(func_info)
        prompt = (
            f"{user_message}\n\n"
            "DeepAgents 内置文件系统已绑定到待审计项目根目录。"
            "请使用内置 ls、read_file、glob、grep 读取和搜索源码；所有路径都必须以 / 开头，"
            "其中 / 表示 config.project_path。"
            "请使用 project_go_to_def、project_find_refs、project_skill 处理符号导航和项目知识。"
            "完成后按结构化输出返回 code_logic 和 code_map。"
        )

        if getattr(self.trace_agent, "debug", False):
            self.trace_agent._log(f"[DeepAgents] 开始分析：{func_info.func_name}")

        try:
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=self._invoke_config(),
            )
        except GraphRecursionError as exc:
            return self._recursion_fallback(func_info, exc)
        messages = self._serialize_messages(result.get("messages", [])) if isinstance(result, dict) else []
        try:
            output = self._extract_output(result)
        except ValidationError as exc:
            return self._unstructured_fallback(func_info, messages, exc)
        return output.code_logic, output.code_map, messages

    @property
    def agent(self):
        if self._agent is None:
            from deepagents import create_deep_agent

            self._agent = create_deep_agent(
                model=self._build_model(),
                tools=make_project_tools(
                    self.audit_function_name,
                    tool_guard=self._get_tool_guard(),
                ),
                system_prompt=self._system_prompt(),
                backend=self._build_backend(),
                permissions=self._filesystem_permissions(),
                response_format=DeepTraceOutput,
                debug=getattr(self.trace_agent, "debug", False),
                name="trace-explorer",
            )
        return self._agent

    def _build_model(self):
        from utils.chat_model import build_chat_model

        return build_chat_model()

    def _build_backend(self):
        from config import get_config
        from deepagents.backends import FilesystemBackend
        from utils.logged_backend import LoggedBackend

        config = get_config()
        project_path = Path(config.project_path).expanduser().resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"config.project_path does not exist: {project_path}")
        if not project_path.is_dir():
            raise NotADirectoryError(f"config.project_path is not a directory: {project_path}")

        return LoggedBackend(
            FilesystemBackend(root_dir=project_path, virtual_mode=True),
            prefix="trace_fs",
            audit_function_name=self.audit_function_name,
            max_tool_calls=config.max_tool_calls,
            max_repeated_calls=config.max_repeated_tool_calls,
            tool_guard=self._get_tool_guard(),
        )

    def _get_tool_guard(self) -> ToolCallGuard:
        if self._tool_guard is None:
            from config import get_config

            config = get_config()
            self._tool_guard = ToolCallGuard(
                max_tool_calls=config.max_tool_calls,
                max_repeated_calls=config.max_repeated_tool_calls,
            )
        return self._tool_guard

    def _invoke_config(self) -> dict:
        return build_deepagents_invoke_config()

    def _recursion_fallback(
        self,
        func_info: FunctionInfo,
        exc: GraphRecursionError,
    ) -> tuple[str, List[CodeContext], List[Dict[str, Any]]]:
        message = (
            f"{recursion_limit_message('Trace 探索阶段')} "
            "本次仅保留入口函数上下文，后续审计结果应按低置信度处理。"
        )
        if getattr(self.trace_agent, "debug", False):
            self.trace_agent._log(f"[DeepAgents] {message} 原始错误: {exc}")

        return (
            message,
            [
                CodeContext(
                    function_name=func_info.func_name,
                    file_path=func_info.file_path,
                    line_start=func_info.start_line,
                    line_end=func_info.end_line,
                    code_snippet=func_info.code_snippet,
                    is_entry_point=True,
                    taint_source=func_info.input,
                    taint_path="DeepAgents trace stopped at graph step limit; entry context only.",
                )
            ],
            [{"role": "system", "content": message}],
        )

    def _unstructured_fallback(
        self,
        func_info: FunctionInfo,
        messages: List[Dict[str, Any]],
        exc: ValidationError,
    ) -> tuple[str, List[CodeContext], List[Dict[str, Any]]]:
        message = (
            "DeepAgents 未返回结构化 code_logic/code_map，已保留原始消息并使用入口函数上下文继续。"
        )
        if getattr(self.trace_agent, "debug", False):
            self.trace_agent._log(f"[DeepAgents] {message} 原始错误: {exc}")

        return (
            message,
            [
                CodeContext(
                    function_name=func_info.func_name,
                    file_path=func_info.file_path,
                    line_start=func_info.start_line,
                    line_end=func_info.end_line,
                    code_snippet=func_info.code_snippet,
                    is_entry_point=True,
                    taint_source=func_info.input,
                    taint_path="DeepAgents returned messages without structured trace output.",
                )
            ],
            messages or [{"role": "system", "content": message}],
        )

    def _filesystem_permissions(self):
        from deepagents import FilesystemPermission

        return [
            FilesystemPermission(
                operations=["write"],
                paths=["/**"],
                mode="deny",
            )
        ]

    def _system_prompt(self) -> str:
        return (
            f"{EXPLORATION_SYSTEM_PROMPT}\n\n"
            "你运行在 DeepAgents 中。DeepAgents 文件系统根目录 / 已绑定到待审计项目的 "
            "config.project_path。请使用内置 ls/read_file/glob/grep 访问源码；"
            "trace 阶段是只读分析，不要尝试写入或编辑文件。"
        )

    def _extract_output(self, result: Any) -> DeepTraceOutput:
        return extract_structured_model(result, DeepTraceOutput)

    def _serialize_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        serialized = []
        for message in messages:
            if isinstance(message, dict):
                serialized.append(message)
                continue
            try:
                from langchain_core.messages import message_to_dict

                serialized.append(message_to_dict(message))
            except Exception:
                serialized.append({
                    "role": getattr(message, "type", type(message).__name__),
                    "content": str(getattr(message, "content", message)),
                })
        return serialized
