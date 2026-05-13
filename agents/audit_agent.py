#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AuditAgent - 审计调度 Agent

接收 trace_agent 的审计请求，根据 audit_type 调度到对应 AuditSpec，
如果发现漏洞则调用 exploit_agent 进行 PoC 验证。
"""

import sys
from typing import List, Optional

from agents.audit_specs import AUDIT_SPECS, AuditSpec
from agents.runtime_factory import create_audit_runner
from models import FunctionInfo, CodeContext, AuditResult, ExploitResult
from utils.runtime_skills import load_attack_surface_skill_metadata
from utils.terminal_status import get_terminal_status


class AuditAgent:
    """
    审计调度 Agent

    负责按 AuditSpec 调度通用 external audit runner 和 exploit agent。
    """

    AUDIT_TYPES = AUDIT_SPECS

    def __init__(
        self,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
        on_log: callable = None,
    ):
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir
        self.on_log = on_log or (lambda x: None)
        from config import get_config
        config = get_config()
        self.config = config
        self.disable_exploit = config.disable_exploit
        self.enable_fallback_audit = config.enable_fallback_audit

    def _log(self, message: str) -> None:
        """输出日志到 stderr 和 TUI"""
        print(message, file=sys.stderr)
        self.on_log(message)

    def audit(self) -> tuple[List[AuditResult], List[ExploitResult]]:
        """
        执行审计：攻击面 skill 绑定 required_audit_types，配置 audit_types 显式追加其它类型。

        Returns:
            (List[AuditResult], List[ExploitResult]) 所有审计结果和利用结果
        """
        all_audit_results = []
        all_exploit_results = []

        specs_to_run = self._select_specs()
        if self.enable_fallback_audit:
            specs_to_run = [*specs_to_run, self._build_fallback_spec(specs_to_run)]

        # 遍历要审计的类型
        for spec in specs_to_run:
            get_terminal_status().set_function_audit(self.function_info.func_name, spec.audit_type)
            self._log(f"[AuditAgent] 开始 {spec.audit_type} 审计")

            audit_results = self._run_single_audit(spec)

            audit_results = self._normalize_audit_results(audit_results)

            if audit_results:
                all_audit_results.extend(audit_results)

                # 如果发现漏洞且置信度较高，调用 exploit agent
                for audit_result in audit_results:
                    if not (
                        spec.enable_exploit
                        and audit_result.is_vulnerable
                        and audit_result.confidence in spec.exploit_confidence
                    ):
                        continue

                    title = f" ({audit_result.title})" if audit_result.title else ""
                    self._log(f"[AuditAgent] 发现 {spec.audit_type} 漏洞{title}，启动 ExploitAgent")

                    if self.disable_exploit:
                        self._log(f"  [Exploit] 已禁用 exploit")
                        exploit_result = None
                    else:
                        exploit_result = self._run_exploit_agent(audit_result)

                        if exploit_result:
                            self._log(f"  [Exploit] 成功: {exploit_result.success}")
                            all_exploit_results.append(exploit_result)
                        else:
                            self._log(f"  [Exploit] 失败: 无法生成利用")

        return all_audit_results, all_exploit_results

    def _select_specs(self) -> List[AuditSpec]:
        """Select audit specs from attack-surface skill bindings plus explicit config."""
        requested = self._requested_audit_types()
        specs = []
        for audit_type in requested:
            spec = self.AUDIT_TYPES.get(audit_type)
            if spec is None:
                self._log(f"[AuditAgent] 未知的审计类型: {audit_type}")
                continue
            specs.append(spec)
        if not specs:
            skill_name = self.function_info.skill or self.config.attack_surface_skill or "-"
            self._log(
                f"[AuditAgent] 没有可运行的正常审计类型: skill={skill_name}, "
                "请在 skill.required_audit_types 或 .env audit_types 中配置"
            )
        return specs

    def _requested_audit_types(self) -> List[str]:
        skill_name = self.function_info.skill or self.config.attack_surface_skill
        requested: list[str] = []
        if skill_name:
            metadata = load_attack_surface_skill_metadata(skill_name)
            requested.extend(metadata.required_audit_types)
        requested.extend(self.config.audit_types or [])
        return list(dict.fromkeys(item for item in requested if item))

    def _build_fallback_spec(self, audited_specs: List[AuditSpec]) -> AuditSpec:
        """动态构造兜底审计 spec；不注册进 AUDIT_SPECS。"""
        audited_types = [spec.audit_type for spec in audited_specs]
        audited_names = [
            f"- {spec.audit_type}: {spec.display_name}"
            for spec in audited_specs
        ]
        audited_type_list = ", ".join(audited_types) or "无"
        audited_name_block = "\n".join(audited_names) or "- 无"

        system_prompt = f"""你是一个代码安全审计专家，负责进行兜底安全审计。

## 任务
正常注册的漏洞类型已经完成审计。本轮只能审计以下已有问题类型以外的安全漏洞，不要重复输出已有类型的问题。

## 已审计的问题类型
{audited_name_block}

## 兜底审计范围
- 关注未被上述类型覆盖的安全问题，例如：认证/授权绕过、敏感信息泄露、越权访问、内存安全、资源耗尽、逻辑缺陷、不安全文件操作、弱随机数、日志/错误信息泄露、竞争条件等。
- 必须从公共 system prompt 中指定的入口函数、Code Map 和项目源码出发，沿当前入口函数相关的数据流或控制流分析。
- 如果发现的问题本质属于已审计类型（{audited_type_list}），不要在兜底审计中重复报告。
- 如果无法证明安全影响，返回低置信度或无漏洞，不要编造问题。

## 输出要求
- 如果发现多个不同的兜底安全问题，必须在 findings 数组中逐条输出。
- 每条 finding 的 title 应清楚说明未覆盖的问题类型或风险点。
- vulnerability_type 会由系统统一标记为 fallback_security；具体问题类别写入 title/description。"""

        user_prompt = f"""## 兜底安全审计任务
请基于公共 system prompt 中的入口函数、Function Skill、Code Map 和项目源码，审计已有问题类型以外的安全漏洞。

已审计类型：{audited_type_list}

不要重复报告上述类型；只输出其它安全风险。"""

        class FallbackAuditSpec:
            audit_type = "fallback_security"
            agent_name = "fallback_security_audit"
            display_name = "兜底安全审计"
            enable_exploit = False
            exploit_confidence = ()
            source_path = None

            def build_system_prompt(self, _func_info, _code_map):
                return system_prompt

            def build_user_message(self, _func_info, _code_map):
                return user_prompt

        return FallbackAuditSpec()

    def _run_single_audit(self, spec: AuditSpec) -> Optional[List[AuditResult]]:
        """运行单个 AuditSpec 对应的通用审计 runner。"""
        try:
            self._log(f"[AuditAgent] 启动 {spec.agent_name}")
            return create_audit_runner(
                agent_name=spec.agent_name,
                vulnerability_type=spec.audit_type,
                function_info=self.function_info,
                code_map=self.code_map,
                system_prompt=spec.build_system_prompt(self.function_info, self.code_map),
                user_message=spec.build_user_message(self.function_info, self.code_map),
                project_path=self.project_path,
                debug=self.debug,
                output_dir=self.output_dir,
            ).run()

        except Exception as e:
            self._log(f"[AuditAgent] {spec.audit_type} 审计失败: {e}")
            return None

    def _normalize_audit_results(self, audit_results) -> List[AuditResult]:
        """Accept the new multi-result contract and old single-result callers."""
        if audit_results is None:
            return []
        if isinstance(audit_results, AuditResult):
            return [audit_results]
        return list(audit_results)

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
            self._log(f"[AuditAgent] Exploit 失败: {e}")
            return None
