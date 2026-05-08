#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command injection audit agent backed by DeepAgents."""

import json
from typing import List

from agents.deepagents_audit_runner import DeepAgentsAuditRunner
from agents.prompt import (
    COMMAND_INJECT_DANGEROUS_FUNCTIONS,
    build_command_inject_system_prompt,
    build_command_inject_user_message,
)
from models import AuditResult, CodeContext, FunctionInfo


class CommandInjectAgent:
    """命令注入漏洞审计 Agent。"""

    DANGEROUS_FUNCTIONS = COMMAND_INJECT_DANGEROUS_FUNCTIONS

    def __init__(
        self,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
    ):
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def audit(self) -> AuditResult:
        return DeepAgentsAuditRunner(
            agent_name="command_inject_agent",
            vulnerability_type="command_injection",
            function_info=self.function_info,
            code_map=self.code_map,
            system_prompt=self._build_system_prompt(),
            user_message=self._build_user_message(),
            project_path=self.project_path,
            debug=self.debug,
            output_dir=self.output_dir,
        ).run()

    def _build_system_prompt(self) -> str:
        return build_command_inject_system_prompt(
            self.function_info.func_name,
            self.DANGEROUS_FUNCTIONS,
        )

    def _build_user_message(self) -> str:
        code_map_str = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False,
        )
        return build_command_inject_user_message(code_map_str)
