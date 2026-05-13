#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify one audit runtime call can produce multiple AuditResult findings."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import agents.agent_runtime_runner as runner_module
from agents.agent_runtime_runner import AgentRuntimeAuditRunner
import agents.audit_agent as audit_agent_module
from agents.audit_agent import AuditAgent
from agents.output_schemas import AuditFindingOutput
from config import init_settings
from models import AuditResult, CodeContext, FunctionInfo


PROJECT_ROOT = Path(__file__).parent.parent


def build_inputs() -> tuple[FunctionInfo, list[CodeContext]]:
    func_info = FunctionInfo(
        func_name="handle_request",
        file_path="src/http.c",
        start_line=10,
        end_line=30,
        code_snippet="void handle_request() {}",
        skill="civetweb_audit",
    )
    code_map = [
        CodeContext(
            function_name="handle_request",
            file_path="src/http.c",
            line_start=10,
            line_end=30,
            code_snippet="void handle_request() {}",
            is_entry_point=True,
            taint_source="query",
            taint_path="query -> cmd",
        )
    ]
    return func_info, code_map


class FakeRuntimeClient:
    def __init__(self, runtime: str, *, project_path: str, debug: bool = False):
        self.runtime = runtime
        self.project_path = project_path
        self.debug = debug

    def run_json(self, *, stage_name, system_prompt, user_prompt, output_model):
        first = AuditFindingOutput(
            title="ping 参数进入 system",
            is_vulnerable=True,
            confidence="high",
            description="ping 参数未过滤后进入 system",
            taint_flow="query.ping -> system",
            recommendation="使用 allowlist 并避免 shell",
        )
        second = AuditFindingOutput(
            title="hostname 参数进入 popen",
            is_vulnerable=True,
            confidence="medium",
            description="hostname 参数未过滤后进入 popen",
            taint_flow="query.hostname -> popen",
            recommendation="改用 execve 参数数组",
        )
        return output_model(
            is_vulnerable=True,
            confidence="high",
            description="发现两处命令注入风险",
            findings=[first, second],
        ), [{"role": "assistant", "content": "fake"}]


def verify_runner_maps_findings_to_multiple_audit_results() -> None:
    init_settings(
        {
            "project_path": str(PROJECT_ROOT),
            "agent_runtime": "codex",
            "target_base_url": "http://example.test",
            "audit_types": ["command_injection"],
        }
    )
    func_info, code_map = build_inputs()
    original_client = runner_module.AgentRuntimeClient
    runner_module.AgentRuntimeClient = FakeRuntimeClient
    try:
        results = AgentRuntimeAuditRunner(
            runtime="codex",
            agent_name="command_injection_audit",
            vulnerability_type="command_injection",
            function_info=func_info,
            code_map=code_map,
            system_prompt="system",
            user_message="user",
            project_path=str(PROJECT_ROOT),
        ).run()
    finally:
        runner_module.AgentRuntimeClient = original_client

    if not isinstance(results, list):
        raise AssertionError("audit runner should return a list of AuditResult findings")
    if len(results) != 2:
        raise AssertionError(f"expected 2 findings, got {len(results)}")
    if [result.taint_flow for result in results] != ["query.ping -> system", "query.hostname -> popen"]:
        raise AssertionError("runner should preserve per-finding taint flows")
    if any(result.vulnerability_type != "command_injection" for result in results):
        raise AssertionError("runner should attach the current vulnerability type to every finding")


class FakeAuditRunner:
    def __init__(self, calls: list[dict], **kwargs):
        self.calls = calls
        self.kwargs = kwargs

    def run(self):
        self.calls.append(self.kwargs)
        return [
            AuditResult(
                vulnerability_type=self.kwargs["vulnerability_type"],
                is_vulnerable=False,
                confidence="low",
                description=f"fake {self.kwargs['vulnerability_type']}",
                code_map=self.kwargs["code_map"],
            )
        ]


def verify_fallback_audit_is_disabled_by_default() -> None:
    init_settings(
        {
            "project_path": str(PROJECT_ROOT),
            "agent_runtime": "codex",
            "target_base_url": "http://example.test",
            "disable_exploit": True,
            "audit_types": [],
        }
    )
    func_info, code_map = build_inputs()
    calls: list[dict] = []
    original_create_audit_runner = audit_agent_module.create_audit_runner
    audit_agent_module.create_audit_runner = lambda **kwargs: FakeAuditRunner(calls, **kwargs)
    try:
        AuditAgent(func_info, code_map, project_path=str(PROJECT_ROOT)).audit()
    finally:
        audit_agent_module.create_audit_runner = original_create_audit_runner

    if [call["vulnerability_type"] for call in calls] != [
        "command_injection",
        "path_traversal",
        "brute_force",
        "password_reset",
        "loop",
    ]:
        raise AssertionError("skill required_audit_types should run when fallback is disabled")


def verify_fallback_audit_runs_after_registered_types_when_enabled() -> None:
    init_settings(
        {
            "project_path": str(PROJECT_ROOT),
            "agent_runtime": "codex",
            "target_base_url": "http://example.test",
            "disable_exploit": True,
            "enable_fallback_audit": True,
            "audit_types": [],
        }
    )
    func_info, code_map = build_inputs()
    calls: list[dict] = []
    original_create_audit_runner = audit_agent_module.create_audit_runner
    audit_agent_module.create_audit_runner = lambda **kwargs: FakeAuditRunner(calls, **kwargs)
    try:
        AuditAgent(func_info, code_map, project_path=str(PROJECT_ROOT)).audit()
    finally:
        audit_agent_module.create_audit_runner = original_create_audit_runner

    called_types = [call["vulnerability_type"] for call in calls]
    if called_types != [
        "command_injection",
        "path_traversal",
        "brute_force",
        "password_reset",
        "loop",
        "fallback_security",
    ]:
        raise AssertionError(f"unexpected audit call order: {called_types}")
    fallback_prompt = calls[-1]["system_prompt"]
    if "command_injection" not in fallback_prompt or "path_traversal" not in fallback_prompt:
        raise AssertionError("fallback prompt should include already-audited vulnerability types")
    if "以外" not in fallback_prompt:
        raise AssertionError("fallback prompt should instruct the model to audit outside existing types")


if __name__ == "__main__":
    verify_runner_maps_findings_to_multiple_audit_results()
    verify_fallback_audit_is_disabled_by_default()
    verify_fallback_audit_runs_after_registered_types_when_enabled()
    print("multi-finding audit verification passed")
