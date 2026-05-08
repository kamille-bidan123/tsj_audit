#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepAgents-backed runner for vulnerability-specific audit agents."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from agents.deepagents_trace_explorer import (
    make_project_tools,
)
from models import AuditResult, CodeContext, FunctionInfo
from utils.deepagents_runtime import (
    GraphRecursionError,
    build_deepagents_invoke_config,
    recursion_limit_message,
)
from utils.deepagents_output import extract_structured_model
from utils.tool_call_guard import ToolCallGuard


class DeepAuditOutput(BaseModel):
    """Structured output expected from a DeepAgents audit run."""

    is_vulnerable: bool = Field(description="是否存在漏洞")
    confidence: str = Field(description="漏洞置信度：high、medium 或 low")
    description: str = Field(default="", description="漏洞描述")
    summary: str = Field(default="", description="审计发现总结")
    taint_flow: Optional[str] = Field(default=None, description="污点流向")
    recommendation: Optional[str] = Field(default=None, description="修复建议")
    code_map: List[CodeContext] = Field(
        default_factory=list,
        description="相关代码上下文列表",
    )


class DeepAgentsAuditRunner:
    """Shared DeepAgents runtime for all vulnerability-specific audit agents."""

    def __init__(
        self,
        *,
        agent_name: str,
        vulnerability_type: str,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        system_prompt: str,
        user_message: str,
        project_path: str,
        debug: bool = False,
        output_dir: str | None = None,
    ):
        self.agent_name = agent_name
        self.vulnerability_type = vulnerability_type
        self.function_info = function_info
        self.code_map = code_map
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir
        self._agent = None
        self._tool_guard = None
        self.tools = make_project_tools(
            function_info.func_name,
            tool_guard=self._get_tool_guard(),
        )

    def run(self) -> AuditResult:
        if self.debug:
            print(f"\n[{self.agent_name}] DeepAgents 审计开始", file=sys.stderr)

        try:
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": self._user_prompt()}]},
                config=self._invoke_config(),
            )
            messages = self._serialize_messages(result.get("messages", [])) if isinstance(result, dict) else []
            try:
                output = self._extract_output(result)
            except ValidationError as exc:
                output = self._unstructured_fallback_output(exc)
                messages = messages or [{"role": "system", "content": output.description}]
        except GraphRecursionError as exc:
            output = self._recursion_fallback_output(exc)
            messages = [{"role": "system", "content": output.description}]
        self._save_conversation_history(messages)
        return self._to_audit_result(output)

    @property
    def agent(self):
        if self._agent is None:
            from deepagents import create_deep_agent

            self._agent = create_deep_agent(
                model=self._build_model(),
                tools=self.tools,
                system_prompt=self._system_prompt(),
                backend=self._build_backend(),
                permissions=self._filesystem_permissions(),
                response_format=DeepAuditOutput,
                debug=self.debug,
                name=self.agent_name,
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
        configured_path = self.project_path
        if not configured_path or configured_path == ".":
            configured_path = config.project_path
        project_path = Path(configured_path).expanduser().resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"project_path does not exist: {project_path}")
        if not project_path.is_dir():
            raise NotADirectoryError(f"project_path is not a directory: {project_path}")

        return LoggedBackend(
            FilesystemBackend(root_dir=project_path, virtual_mode=True),
            prefix=f"{self.agent_name}_fs",
            audit_function_name=self.function_info.func_name,
            max_tool_calls=config.max_tool_calls,
            max_repeated_calls=config.max_repeated_tool_calls,
            blocked_grep_patterns=self._blocked_grep_patterns(),
            tool_guard=self._get_tool_guard(),
        )

    def _get_tool_guard(self) -> ToolCallGuard:
        if self._tool_guard is None:
            from config import get_config

            config = get_config()
            self._tool_guard = ToolCallGuard(
                max_tool_calls=config.max_tool_calls,
                max_repeated_calls=config.max_repeated_tool_calls,
                blocked_grep_patterns=self._blocked_grep_patterns(),
            )
        return self._tool_guard

    def _invoke_config(self) -> dict:
        return build_deepagents_invoke_config()

    def _recursion_fallback_output(self, exc: GraphRecursionError) -> DeepAuditOutput:
        message = (
            f"{recursion_limit_message(f'{self.agent_name} 审计阶段')} "
            "已返回低置信度未确认结果，避免单个接口阻塞整体审计。"
        )
        if self.debug:
            print(f"[{self.agent_name}] {message} 原始错误: {exc}", file=sys.stderr)

        return DeepAuditOutput(
            is_vulnerable=False,
            confidence="low",
            description=message,
            summary=message,
            code_map=self.code_map,
        )

    def _unstructured_fallback_output(self, exc: ValidationError) -> DeepAuditOutput:
        message = (
            f"{self.agent_name} 未返回结构化审计结果，已返回低置信度未确认结果。"
        )
        if self.debug:
            print(f"[{self.agent_name}] {message} 原始错误: {exc}", file=sys.stderr)

        return DeepAuditOutput(
            is_vulnerable=False,
            confidence="low",
            description=message,
            summary=message,
            code_map=self.code_map,
        )

    def _blocked_grep_patterns(self) -> set[str]:
        if self.vulnerability_type != "command_injection":
            return set()
        return {
            "system*",
            "popen*",
            "exec*",
        }

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
            f"{self.system_prompt}\n\n"
            "## DeepAgents Runtime\n"
            "- 文件系统根目录 / 已绑定到待审计项目根目录，也就是 config.project_path。\n"
            "- 使用 DeepAgents 内置 ls/read_file/glob/grep 读取和搜索源码；路径必须以 / 开头。\n"
            "- 使用 project_go_to_def、project_find_refs、project_skill 做符号导航和项目知识读取。\n"
            "- 禁止对同一 pattern/path/glob 重复调用 grep；如果工具提示重复或达到上限，必须停止工具循环并直接总结。\n"
            "- 不要使用旧 submit_*、read_file/list_dir/search_code function-calling 协议。\n"
            "- 审计阶段是只读分析，不要写入、编辑或删除文件。\n"
            "- 完成后直接按结构化输出返回 is_vulnerable、confidence、description、"
            "taint_flow、recommendation、code_map。"
        )

    def _user_prompt(self) -> str:
        return (
            f"{self.user_message}\n\n"
            "请基于上述 codemap 和必要的项目源码继续审计。"
            "如果需要源码，使用 DeepAgents 内置 read_file/ls/glob/grep；"
            "如果需要沿调用关系追踪，使用 project_go_to_def/project_find_refs。"
            "完成后直接返回结构化审计结果。"
        )

    def _extract_output(self, result: Any) -> DeepAuditOutput:
        return extract_structured_model(result, DeepAuditOutput)

    def _to_audit_result(self, output: DeepAuditOutput) -> AuditResult:
        description = output.description or output.summary or "审计未提供描述"
        return AuditResult(
            vulnerability_type=self.vulnerability_type,
            is_vulnerable=output.is_vulnerable,
            confidence=output.confidence,
            description=description,
            taint_flow=output.taint_flow,
            recommendation=output.recommendation,
            code_map=output.code_map or self.code_map,
        )

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

    def _save_conversation_history(self, messages: List[Dict[str, Any]]) -> None:
        if not self.output_dir:
            return

        conversations_dir = Path(self.output_dir) / "conversations" / self.agent_name
        conversations_dir.mkdir(parents=True, exist_ok=True)

        safe_func_name = "".join(
            c if c.isalnum() or c in ("_", "-") else "_"
            for c in self.function_info.func_name
        )
        conversation_file = conversations_dir / f"{safe_func_name}.json"

        conversation_data = {
            "function_info": self.function_info.model_dump(),
            "conversation_history": messages,
            "saved_at": datetime.now().isoformat(),
            "agent": self.agent_name,
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)
