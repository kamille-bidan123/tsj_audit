#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opencode/Codex/Claude Code-backed runners for audit stages."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Union

from pydantic import ValidationError

from agents.output_schemas import AuditOutput, EntryDiscoveryOutput, ExploitOutput, TraceOutput
from agents.prompt import EXPLORATION_SYSTEM_PROMPT, build_exploration_user_message
from agents.runtime_clients import AgentRuntimeClient
from models import AuditResult, CodeContext, EntrySpec, ExploitResult, FunctionInfo
from utils.runtime_skills import build_attack_surface_skill_usage_prompt, build_skill_usage_prompt
from utils.terminal_status import get_terminal_status


RUNTIME_RETRY_ATTEMPTS = 3


class AgentRuntimeEntryDiscoveryRunner:
    """Attack-surface entry discovery backed by opencode/Codex/Claude Code."""

    def __init__(
        self,
        *,
        runtime: str,
        attack_surface_skill: str,
        project_path: str,
        debug: bool = False,
        output_dir: str | None = None,
    ):
        self.runtime = runtime
        self.attack_surface_skill = attack_surface_skill
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def run(self) -> List[EntrySpec]:
        get_terminal_status().set_stage("Entry Discovery", function_name="-", audit_type="-")
        print(
            f"[EntryDiscovery] runtime={self.runtime} skill={self.attack_surface_skill} 开始",
            file=sys.stderr,
            flush=True,
        )
        client = AgentRuntimeClient(self.runtime, project_path=self.project_path, debug=self.debug)
        output, _messages = client.run_json(
            stage_name="entry_discovery",
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(),
            output_model=EntryDiscoveryOutput,
        )
        discovery_output = EntryDiscoveryOutput.model_validate(output)
        entries = self._normalize_entries(discovery_output.functions)
        print(
            f"[EntryDiscovery] runtime={self.runtime} 完成，发现 {len(entries)} 个入口",
            file=sys.stderr,
            flush=True,
        )
        return entries

    def _normalize_entries(self, entries: List[EntrySpec]) -> List[EntrySpec]:
        normalized = []
        for entry in entries:
            if entry.skill != self.attack_surface_skill:
                entry = entry.model_copy(update={"skill": self.attack_surface_skill})
            normalized.append(entry)
        return normalized

    def _system_prompt(self) -> str:
        skill_prompt = build_attack_surface_skill_usage_prompt(
            self.attack_surface_skill,
            runtime=self.runtime,
            project_path=self.project_path,
        )
        return f"""你是攻击面入口发现 Agent，负责根据指定 attack surface skill 在项目源码中发现所有审计入口函数。

{skill_prompt}

## Discovery Contract
- 必须读取 `{self.attack_surface_skill}` skill。
- skill 必须包含：攻击面发现知识、外部输入知识、PoC 生成知识。
- 本阶段只输出包含 functions 字段的 JSON object，不做漏洞审计，不输出 Markdown。
- 必须根据 skill 的“攻击面发现知识”搜索源码中的注册点、回调、handler 或入口函数。
- 每个入口输出轻量 EntrySpec：func_name、file_path、skill；如果可以定位，尽量包含 start_line。
- 每个 EntrySpec.skill 必须设置为 `{self.attack_surface_skill}`。
- C++ 成员函数名必须尽量使用 ClassName::methodName，避免同名 handle 方法混淆。
- 找不到真实函数或文件的候选不要输出。
- 不要编造入口函数；没有发现入口时返回 {{"functions": []}}。"""

    def _user_prompt(self) -> str:
        return "请根据 attack surface skill 自动发现该攻击面的所有接口入口函数，并返回 JSON object：{\"functions\": EntrySpec[]}。"


class AgentRuntimeTraceExplorer:
    """Trace exploration backed by opencode/Codex/Claude Code."""

    def __init__(self, trace_agent, *, runtime: str):
        self.trace_agent = trace_agent
        self.runtime = runtime

    def run(self, entry: Union[EntrySpec, FunctionInfo]) -> tuple[FunctionInfo, str, List[CodeContext], List[Dict[str, Any]]]:
        from config import get_config

        config = get_config()
        log = getattr(self.trace_agent, "_log", None)
        if callable(log):
            log(f"[TraceRuntime] runtime={self.runtime} 开始 trace: {entry.func_name}")
        get_terminal_status().set_stage("Trace", function_name=entry.func_name, audit_type="-")
        client = AgentRuntimeClient(
            self.runtime,
            project_path=config.project_path,
            debug=getattr(self.trace_agent, "debug", False),
        )
        last_exc: Exception | None = None
        for attempt in range(1, RUNTIME_RETRY_ATTEMPTS + 1):
            try:
                output, messages = client.run_json(
                    stage_name="trace",
                    system_prompt=self._system_prompt(entry, project_path=config.project_path),
                    user_prompt=self._user_prompt(),
                    output_model=TraceOutput,
                )
                trace_output = TraceOutput.model_validate(output)
                break
            except (RuntimeError, ValidationError, ValueError) as exc:
                last_exc = exc
                if attempt < RUNTIME_RETRY_ATTEMPTS:
                    self._log_runtime_failure(
                        f"{self.runtime} trace runtime attempt {attempt}/{RUNTIME_RETRY_ATTEMPTS} failed: {exc}; retrying"
                    )
        else:
            return self._fallback(entry, last_exc or RuntimeError("trace runtime failed"))
        if callable(log):
            log(f"[TraceRuntime] runtime={self.runtime} 完成 trace: {trace_output.function_info.func_name}")
        return trace_output.function_info, trace_output.code_logic, trace_output.code_map, messages

    def _fallback(self, entry: Union[EntrySpec, FunctionInfo], exc: Exception):
        message = f"{self.runtime} trace runtime failed: {exc}"
        self._log_runtime_failure(message)
        func_info = self._fallback_function_info(entry)
        return (
            func_info,
            message,
            [
                CodeContext(
                    function_name=func_info.func_name,
                    file_path=func_info.file_path,
                    line_start=func_info.start_line,
                    line_end=func_info.end_line,
                    code_snippet=func_info.code_snippet,
                    is_entry_point=True,
                    taint_source=func_info.skill or "unknown",
                    taint_path=f"{self.runtime} runtime failed; entry context only.",
                )
            ],
            [{"role": "system", "content": message}],
        )

    def _log_runtime_failure(self, message: str) -> None:
        log = getattr(self.trace_agent, "_log", None)
        if callable(log):
            log(f"[{self.runtime}] {message}")
        else:
            print(f"[{self.runtime}] {message}", file=sys.stderr)

    def _fallback_function_info(self, entry: Union[EntrySpec, FunctionInfo]) -> FunctionInfo:
        if isinstance(entry, FunctionInfo):
            return entry
        start_line = entry.start_line or 1
        return FunctionInfo(
            func_name=entry.func_name,
            file_path=entry.file_path,
            start_line=start_line,
            end_line=start_line,
            code_snippet="",
            skill=entry.skill,
        )

    def _system_prompt(self, entry: Union[EntrySpec, FunctionInfo], *, project_path: str) -> str:
        skill_prompt = build_skill_usage_prompt(
            self._fallback_function_info(entry),
            runtime=self.runtime,
            project_path=project_path,
        )
        entry_json = json.dumps(entry.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
        entry_kind = "FunctionInfo" if isinstance(entry, FunctionInfo) else "EntrySpec"
        return f"""{EXPLORATION_SYSTEM_PROMPT}

## Trace Entry
当前输入类型：{entry_kind}

```json
{entry_json}
```

## FunctionInfo 补齐要求
你必须先根据 Trace Entry 和项目源码补齐完整 FunctionInfo，并在最终 JSON 的 `function_info` 字段返回。

补齐规则：
1. 如果 EntrySpec 的 `file_path + start_line` 指向入口函数体开头：读取该文件，从该函数开始处向后查看，确认函数结束位置，补齐 `end_line` 和完整 `code_snippet`。
2. 如果 EntrySpec 的 `file_path + start_line` 指向回调/handler/route 注册位置：先读取该注册点，识别真实 callback 或 handler 函数，再在项目中查找它的定义位置，补齐真实入口函数的 `file_path`、`start_line`、`end_line` 和完整 `code_snippet`。
3. 如果输入已经是完整 FunctionInfo，也要核对源码；若发现行号或片段不一致，以项目源码为准输出修正后的 `function_info`。
4. `function_info.skill` 必须保留 Entry 中的 skill。不要输出 input 字段。

{skill_prompt}

## Trace Field Injection Rules
- 所有 EntrySpec、FunctionInfo、代码片段、skill 路径等字段只在本 system prompt 中注入。
- user task 不包含任何入口字段，必须以本 system prompt 为准。
- 具体 taint_source 必须来自当前代码里的变量、参数或 API 调用，不要把 skill 文档当成污染源。"""

    def _user_prompt(self) -> str:
        return (
            f"{build_exploration_user_message()}\n\n"
            "请读取项目源码，先补齐 function_info，再基于补齐后的入口输出 code_logic/code_map。"
        )


class AgentRuntimeAuditRunner:
    """Vulnerability audit backed by opencode/Codex/Claude Code."""

    def __init__(
        self,
        *,
        runtime: str,
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
        self.runtime = runtime
        self.agent_name = agent_name
        self.vulnerability_type = vulnerability_type
        self.function_info = function_info
        self.code_map = code_map
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def run(self) -> List[AuditResult]:
        get_terminal_status().set_stage("Audit", function_name=self.function_info.func_name, audit_type=self.vulnerability_type)
        print(
            f"[AuditRuntime] runtime={self.runtime} agent={self.agent_name} 开始",
            file=sys.stderr,
            flush=True,
        )
        client = AgentRuntimeClient(self.runtime, project_path=self.project_path, debug=self.debug)
        last_exc: Exception | None = None
        for attempt in range(1, RUNTIME_RETRY_ATTEMPTS + 1):
            try:
                output, _messages = client.run_json(
                    stage_name=self.agent_name,
                    system_prompt=self._system_prompt(),
                    user_prompt=self._user_prompt(),
                    output_model=AuditOutput,
                )
                audit_output = AuditOutput.model_validate(output)
                break
            except (RuntimeError, ValidationError, ValueError) as exc:
                last_exc = exc
                if attempt < RUNTIME_RETRY_ATTEMPTS:
                    print(
                        f"[AuditRuntime] runtime={self.runtime} agent={self.agent_name} "
                        f"attempt {attempt}/{RUNTIME_RETRY_ATTEMPTS} failed: {exc}; retrying",
                        file=sys.stderr,
                        flush=True,
                    )
        else:
            output = self._fallback_output(last_exc or RuntimeError("audit runtime failed"))
            audit_output = AuditOutput.model_validate(output)
        results = self._audit_results_from_output(audit_output)
        print(
            f"[AuditRuntime] runtime={self.runtime} agent={self.agent_name} 完成，结果 {len(results)} 条",
            file=sys.stderr,
            flush=True,
        )
        return results

    def _audit_results_from_output(self, audit_output: AuditOutput) -> List[AuditResult]:
        """Map one runtime response into one or more concrete audit findings."""
        if audit_output.findings:
            results = []
            for index, finding in enumerate(audit_output.findings, 1):
                results.append(
                    AuditResult(
                        vulnerability_type=self.vulnerability_type,
                        finding_id=finding.finding_id or f"{self.vulnerability_type}-{index}",
                        title=finding.title or f"{self.vulnerability_type} finding {index}",
                        severity=finding.severity,
                        is_vulnerable=finding.is_vulnerable,
                        confidence=finding.confidence,
                        description=finding.description or finding.title or "审计未提供描述",
                        taint_flow=finding.taint_flow,
                        recommendation=finding.recommendation,
                        code_map=finding.code_map or self.code_map,
                    )
                )
            return results

        return [
            AuditResult(
                vulnerability_type=self.vulnerability_type,
                is_vulnerable=audit_output.is_vulnerable,
                confidence=audit_output.confidence,
                description=audit_output.description or audit_output.summary or "审计未提供描述",
                taint_flow=audit_output.taint_flow,
                recommendation=audit_output.recommendation,
                code_map=audit_output.code_map or self.code_map,
            )
        ]

    def _system_prompt(self) -> str:
        skill_prompt = build_skill_usage_prompt(
            self.function_info,
            runtime=self.runtime,
            project_path=self.project_path,
        )
        return (
            "## Unified System Prompt\n"
            f"{self._common_system_prompt()}\n\n"
            f"{skill_prompt}\n\n"
            "## Vulnerability-Specific Audit Rules\n"
            f"{self.system_prompt}\n\n"
            "## Runtime Guardrails\n"
            "- 禁止全局搜索 system/popen/exec* 等危险函数名；必须从入口函数数据流追踪。\n"
            "- 同一漏洞类型下如果发现多个独立 source/sink 或污点路径，必须在 findings 数组中逐条输出。\n"
            "- 如果没有发现该漏洞类型的问题，findings 返回空数组，并用顶层字段给出未发现结论。\n"
            "- 如果工具或外部 runtime 失败，请返回低置信度未确认结果，不要编造漏洞。"
        )

    def _user_prompt(self) -> str:
        return (
            f"{self.user_message}\n\n"
            "请基于 system prompt 中的公共上下文、code_map 和项目源码审计，并返回结构化审计结果。"
        )

    def _common_system_prompt(self) -> str:
        func_info = self.function_info
        code_map_json = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False,
        )
        return f"""## Common Audit Context
你是代码安全审计专家。当前审计是针对一个入口函数和一个漏洞类型的独立判断。

### Entry Function
- 函数名：{func_info.func_name}
- 文件：{func_info.file_path}
- 行号：{func_info.start_line}-{func_info.end_line}
- Function Skill：{func_info.skill or "未指定"}
- 漏洞类型：{self.vulnerability_type}

### Entry Code
```c
{func_info.code_snippet}
```

### Code Map JSON
```json
{code_map_json}
```

### Common Analysis Rules
- 只分析当前入口函数相关的数据流和代码路径。
- `Code Map JSON` 是 trace 阶段给出的候选上下文；可继续读取源码核实，但不要偏离入口函数。
- 具体 taint_source 必须来自当前代码里的变量、参数或 API 调用，不要把 skill 文档当成污染源。
- 如果无法证明外部输入从入口函数传播到敏感操作，应输出低置信度或无漏洞。"""

    def _fallback_output(self, exc: Exception) -> AuditOutput:
        message = f"{self.runtime} {self.agent_name} failed: {exc}"
        print(f"[{self.agent_name}] {message}", file=sys.stderr)
        return AuditOutput(
            is_vulnerable=False,
            confidence="low",
            description=message,
            summary=message,
            code_map=self.code_map,
        )


class AgentRuntimeExploitRunner:
    """Exploit verification backed by opencode/Codex/Claude Code."""

    def __init__(
        self,
        *,
        runtime: str,
        audit_result: AuditResult,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        system_prompt: str,
        user_message: str,
        project_path: str,
        debug: bool = False,
        output_dir: str | None = None,
    ):
        self.runtime = runtime
        self.audit_result = audit_result
        self.function_info = function_info
        self.code_map = code_map
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def run(self) -> ExploitResult:
        get_terminal_status().set_stage("Exploit", function_name=self.function_info.func_name, audit_type=self.audit_result.vulnerability_type)
        print(
            f"[ExploitRuntime] runtime={self.runtime} 开始: {self.audit_result.vulnerability_type}",
            file=sys.stderr,
            flush=True,
        )
        client = AgentRuntimeClient(self.runtime, project_path=self.project_path, debug=self.debug)
        last_exc: Exception | None = None
        for attempt in range(1, RUNTIME_RETRY_ATTEMPTS + 1):
            try:
                output, _messages = client.run_json(
                    stage_name="exploit",
                    system_prompt=self._system_prompt(),
                    user_prompt=self.user_message,
                    output_model=ExploitOutput,
                )
                exploit_output = ExploitOutput.model_validate(output)
                break
            except (RuntimeError, ValidationError, ValueError) as exc:
                last_exc = exc
                if attempt < RUNTIME_RETRY_ATTEMPTS:
                    print(
                        f"[ExploitRuntime] runtime={self.runtime} "
                        f"attempt {attempt}/{RUNTIME_RETRY_ATTEMPTS} failed: {exc}; retrying",
                        file=sys.stderr,
                        flush=True,
                    )
        else:
            output = self._fallback_output(last_exc or RuntimeError("exploit runtime failed"))
            exploit_output = ExploitOutput.model_validate(output)
        result = ExploitResult(
            vulnerability_type=self.audit_result.vulnerability_type,
            success=exploit_output.success,
            poc_command=exploit_output.poc_command,
            output=exploit_output.summary,
            error=exploit_output.error,
        )
        print(
            f"[ExploitRuntime] runtime={self.runtime} 完成: success={result.success}",
            file=sys.stderr,
            flush=True,
        )
        return result

    def _system_prompt(self) -> str:
        skill_prompt = build_skill_usage_prompt(
            self.function_info,
            runtime=self.runtime,
            project_path=self.project_path,
        )
        if not skill_prompt:
            return self.system_prompt
        return (
            f"{self.system_prompt}\n\n"
            f"{skill_prompt}\n\n"
            "## Exploit Skill Rule\n"
            "- PoC 验证前必须结合 Function Skill 中的输入来源、协议/接口语义和安全验证约束。\n"
            "- 不要把 skill 文档本身当成漏洞证据；PoC 必须对应当前 finding 的真实入口、参数和代码路径。"
        )

    def _fallback_output(self, exc: Exception) -> ExploitOutput:
        message = f"{self.runtime} exploit runtime failed: {exc}"
        print(f"[ExploitAgent] {message}", file=sys.stderr)
        return ExploitOutput(
            success=False,
            poc_command="",
            summary=message,
            error=message,
        )
