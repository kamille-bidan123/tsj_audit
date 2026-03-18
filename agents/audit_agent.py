#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AuditAgent - 审计调度 Agent

接收 trace_agent 的审计请求，根据 audit_type 调度到具体的审计 sub-agent，
如果发现漏洞则调用 exploit_agent 进行 PoC 验证。
"""

import sys
from typing import List, Optional

from models import FunctionInfo, CodeContext, AuditResult, ExploitResult


class AuditAgent:
    """
    审计调度 Agent

    负责调度具体的审计 agent 和 exploit agent
    """

    # 支持的审计类型
    AUDIT_TYPES = {
        "command_injection": {
            "agent_module": "agents.command_inject_agent",
            "agent_class": "CommandInjectAgent",
        },
        "path_traversal": {
            "agent_module": "agents.path_traversal_agent",
            "agent_class": "PathTraversalAgent",
        },
        "brute_force": {
            "agent_module": "agents.brute_force_agent",
            "agent_class": "BruteForceAgent",
        },
        "password_reset": {
            "agent_module": "agents.password_reset_agent",
            "agent_class": "PasswordResetAgent",
        },
    }

    def __init__(
        self,
        audit_type: str,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        project_path: str = ".",
        debug: bool = False,
    ):
        self.audit_type = audit_type
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug

    def audit(self) -> tuple[Optional[AuditResult], Optional[ExploitResult]]:
        """
        执行审计

        Returns:
            (AuditResult, ExploitResult) 审计结果和利用结果
        """
        audit_result = None
        exploit_result = None

        # 1. 调度到具体的审计 agent
        audit_result = self._run_audit_agent()

        # 2. 如果发现漏洞且置信度较高，调用 exploit agent
        if audit_result and audit_result.is_vulnerable and audit_result.confidence in ("high", "medium"):
            print(f"\n[AuditAgent] 发现漏洞，启动 ExploitAgent", file=sys.stderr)

            exploit_result = self._run_exploit_agent(audit_result)

            if exploit_result:
                print(f"  [Exploit] 成功: {exploit_result.success}", file=sys.stderr)
            else:
                print(f"  [Exploit] 失败: 无法生成利用", file=sys.stderr)

        return audit_result, exploit_result

    def _run_audit_agent(self) -> Optional[AuditResult]:
        """运行具体的审计 agent"""
        if self.audit_type not in self.AUDIT_TYPES:
            if self.debug:
                print(f"[AuditAgent] 未知的审计类型: {self.audit_type}", file=sys.stderr)
            return None

        config = self.AUDIT_TYPES[self.audit_type]

        try:
            # 动态导入对应的 agent
            module = __import__(config["agent_module"], fromlist=[config["agent_class"]])
            agent_class = getattr(module, config["agent_class"])

            # 初始化并运行
            agent = agent_class(
                function_info=self.function_info,
                code_map=self.code_map,
                project_path=self.project_path,
                debug=self.debug,
            )

            if self.debug:
                print(f"\n[AuditAgent] 启动 {config['agent_class']}", file=sys.stderr)

            return agent.audit()

        except Exception as e:
            if self.debug:
                print(f"[AuditAgent] 审计失败: {e}", file=sys.stderr)
            return None

    def _run_exploit_agent(self, audit_result: AuditResult) -> Optional[ExploitResult]:
        """运行 exploit agent"""
        try:
            from agents.exploit_agent import ExploitAgent

            agent = ExploitAgent(
                audit_result=audit_result,
                function_info=self.function_info,
                code_map=self.code_map,
                project_path=self.project_path,
                debug=self.debug,
            )

            return agent.exploit()

        except Exception as e:
            if self.debug:
                print(f"[AuditAgent] Exploit 失败: {e}", file=sys.stderr)
            return None