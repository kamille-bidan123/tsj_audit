#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AuditAgent - 审计调度 Agent

接收 trace_agent 的审计请求，根据 audit_type 调度到具体的审计 sub-agent，
如果发现漏洞则调用 exploit_agent 进行 PoC 验证。
"""

import sys
from typing import List, Optional
import traceback

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
        "loop": {
            "agent_module": "agents.loop_vulnerability_agent",
            "agent_class": "LoopVulnerabilityAgent",
        },
    }

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
        from config import get_config
        self.disable_exploit = get_config().disable_exploit

    def audit(self) -> tuple[List[AuditResult], List[ExploitResult]]:
        """
        执行审计，根据 function_info.audit_types 选择要审计的类型

        Returns:
            (List[AuditResult], List[ExploitResult]) 所有审计结果和利用结果
        """
        all_audit_results = []
        all_exploit_results = []

        # 根据 audit_types 确定要审计的类型
        if self.function_info.audit_types:
            # 使用指定的审计类型
            audit_types_to_run = [
                at for at in self.function_info.audit_types
                if at in self.AUDIT_TYPES
            ]
        else:
            # 如果没有指定，默认审计所有类型
            audit_types_to_run = list(self.AUDIT_TYPES.keys())

        # 遍历要审计的类型
        for audit_type in audit_types_to_run:
            print(f"\n[AuditAgent] 开始 {audit_type} 审计", file=sys.stderr)

            audit_result = self._run_single_audit(audit_type)

            if audit_result:
                all_audit_results.append(audit_result)

                # 如果发现漏洞且置信度较高，调用 exploit agent
                if audit_result.is_vulnerable and audit_result.confidence in ("high", "medium"):
                    print(f"\n[AuditAgent] 发现 {audit_type} 漏洞，启动 ExploitAgent", file=sys.stderr)

                    if self.disable_exploit:
                        print(f"  [Exploit] 已禁用 exploit", file=sys.stderr)
                        exploit_result = None
                    else:
                        exploit_result = self._run_exploit_agent(audit_result)

                        if exploit_result:
                            print(f"  [Exploit] 成功: {exploit_result.success}", file=sys.stderr)
                            all_exploit_results.append(exploit_result)
                        else:
                            print(f"  [Exploit] 失败: 无法生成利用", file=sys.stderr)

        return all_audit_results, all_exploit_results

    def _run_single_audit(self, audit_type: str) -> Optional[AuditResult]:
        """运行具体的审计 agent"""
        if audit_type not in self.AUDIT_TYPES:
            if self.debug:
                print(f"[AuditAgent] 未知的审计类型: {audit_type}", file=sys.stderr)
            return None

        config = self.AUDIT_TYPES[audit_type]

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
                output_dir=self.output_dir,
            )

            if self.debug:
                print(f"\n[AuditAgent] 启动 {config['agent_class']}", file=sys.stderr)

            return agent.audit()

        except Exception as e:
            if self.debug:
                print(f'{traceback.format_exc()}', file=sys.stderr)
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
                output_dir=self.output_dir,
            )

            return agent.exploit()

        except Exception as e:
            if self.debug:
                print(f"[AuditAgent] Exploit 失败: {e}", file=sys.stderr)
            return None