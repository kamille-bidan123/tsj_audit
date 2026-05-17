#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the current agent-runtime trace pipeline without calling a real LLM."""

from __future__ import annotations

import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.output_schemas import AuditOutput, EntryDiscoveryOutput, TraceOutput
import agents.runtime_factory as runtime_factory
from agents.trace_agent import TraceAgent
from config import get_config, init_settings
from models import AuditResult, CodeContext, EntrySpec, ExploitResult, FunctionInfo
from utils.structured_output import extract_structured_model
from utils.runtime_skills import ensure_runtime_skill, runtime_skill_base_dir

PROJECT_ROOT = Path(__file__).parent.parent


def configure_project_root(**overrides) -> None:
    settings = {
        "project_path": str(PROJECT_ROOT),
        "target_base_url": "http://example.test",
        "agent_runtime": "codex",
    }
    settings.update(overrides)
    init_settings(settings)


class FakeTraceAgent(TraceAgent):
    """Small test double for TraceAgent."""

    def __init__(self):
        self.project_path = str(PROJECT_ROOT)
        self.debug = False
        self.output_dir = None
        self.on_log = lambda _message: None
        self.saved_conversations: List[tuple[str, str, List[Dict]]] = []

    def _audit_codemap(self, func_info: FunctionInfo, code_map: List[CodeContext]):
        return (
            [
                AuditResult(
                    vulnerability_type="command_injection",
                    is_vulnerable=False,
                    confidence="low",
                    description=f"fake audit for {func_info.func_name}",
                    code_map=code_map,
                )
            ],
            [],
        )

    def _save_conversation_history(self, agent_name: str, func_info: FunctionInfo, messages: List[Dict]) -> None:
        self.saved_conversations.append((agent_name, func_info.func_name, messages))


def build_fake_audit_inputs() -> tuple[FunctionInfo, List[CodeContext]]:
    func_info = FunctionInfo(
        func_name="handle_test",
        file_path="src/test.c",
        start_line=10,
        end_line=20,
        code_snippet="int handle_test() { return 0; }",
        skill="civetweb_audit",
    )
    code_map = [
        CodeContext(
            function_name=func_info.func_name,
            file_path=func_info.file_path,
            line_start=func_info.start_line,
            line_end=func_info.end_line,
            code_snippet=func_info.code_snippet,
            is_entry_point=True,
            taint_source=func_info.skill,
            taint_path="fake source -> fake sink",
        )
    ]
    return func_info, code_map


def fake_function_info_dict() -> dict:
    return build_fake_audit_inputs()[0].model_dump()


def verify_trace_agent_pipeline() -> None:
    func_info, _ = build_fake_audit_inputs()

    class FakeExplorer:
        def run(self, entry: EntrySpec):
            func_info = FunctionInfo(
                func_name=entry.func_name,
                file_path=entry.file_path,
                start_line=entry.start_line or 10,
                end_line=20,
                code_snippet="int handle_test() { return 0; }",
                skill=entry.skill,
            )
            return (
                func_info,
                "fake code logic",
                [
                    CodeContext(
                        function_name=func_info.func_name,
                        file_path=func_info.file_path,
                        line_start=func_info.start_line,
                        line_end=func_info.end_line,
                        code_snippet=func_info.code_snippet,
                        is_entry_point=True,
                        taint_source=func_info.skill,
                        taint_path="fake source -> fake sink",
                    )
                ],
                [{"role": "assistant", "content": "fake-codemap"}],
            )

    original_create_trace_explorer = runtime_factory.create_trace_explorer
    runtime_factory.create_trace_explorer = lambda _trace_agent: FakeExplorer()
    try:
        fake_agent = FakeTraceAgent()
        result = fake_agent.audit_function(
            EntrySpec(
                func_name=func_info.func_name,
                file_path=func_info.file_path,
                start_line=func_info.start_line,
                skill=func_info.skill,
            )
        )
    finally:
        runtime_factory.create_trace_explorer = original_create_trace_explorer

    if result.function_info.func_name != "handle_test":
        raise AssertionError("trace pipeline should preserve function info")
    if result.code_logic != "fake code logic":
        raise AssertionError("trace pipeline should preserve trace output")
    if len(result.audit_results) != 1:
        raise AssertionError("trace pipeline should run audit stage")
    if not fake_agent.saved_conversations:
        raise AssertionError("trace pipeline should save trace conversation history")


def verify_trace_runtime_valueerror_falls_back() -> None:
    import tempfile

    from agents import agent_runtime_runner as runner_module
    from agents.agent_runtime_runner import AgentRuntimeTraceExplorer

    class ValueErrorRuntimeClient:
        calls = 0

        def __init__(self, runtime: str, *, project_path: str, debug: bool = False):
            pass

        def run_json(self, **_kwargs):
            self.__class__.calls += 1
            raise ValueError("runtime did not return valid TraceOutput")

    original_client = runner_module.AgentRuntimeClient
    ValueErrorRuntimeClient.calls = 0
    runner_module.AgentRuntimeClient = ValueErrorRuntimeClient
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_project_root(agent_runtime="codex", project_path=tmpdir)
            entry = EntrySpec(
                func_name="handle_test",
                file_path="src/test.c",
                start_line=10,
                skill="civetweb_audit",
            )
            func_info, code_logic, code_map, _messages = AgentRuntimeTraceExplorer(
                FakeTraceAgent(),
                runtime="codex",
            ).run(entry)
    finally:
        runner_module.AgentRuntimeClient = original_client

    if func_info.func_name != "handle_test":
        raise AssertionError("trace fallback should preserve entry function name")
    if ValueErrorRuntimeClient.calls != 3:
        raise AssertionError(f"trace fallback should retry runtime 3 times, got {ValueErrorRuntimeClient.calls}")
    if "runtime did not return valid TraceOutput" not in code_logic:
        raise AssertionError("trace fallback should include the structured output error")
    if len(code_map) != 1 or not code_map[0].is_entry_point:
        raise AssertionError("trace fallback should return an entry-only code map")


def verify_agent_runtime_factory_returns_runtime_runners() -> None:
    from agents.agent_runtime_runner import AgentRuntimeAuditRunner, AgentRuntimeExploitRunner, AgentRuntimeTraceExplorer
    from agents.runtime_factory import create_audit_runner, create_exploit_runner, create_trace_explorer

    func_info, code_map = build_fake_audit_inputs()
    audit_result = AuditResult(
        vulnerability_type="command_injection",
        is_vulnerable=True,
        confidence="medium",
        description="fake vulnerable path",
        code_map=code_map,
    )

    for runtime in ("opencode", "codex", "claudecode"):
        configure_project_root(agent_runtime=runtime)
        if not isinstance(create_trace_explorer(FakeTraceAgent()), AgentRuntimeTraceExplorer):
            raise AssertionError(f"{runtime} trace should use AgentRuntimeTraceExplorer")
        if not isinstance(
            create_audit_runner(
                agent_name="verification_agent",
                vulnerability_type="command_injection",
                function_info=func_info,
                code_map=code_map,
                system_prompt="system",
                user_message="user",
                project_path=str(PROJECT_ROOT),
            ),
            AgentRuntimeAuditRunner,
        ):
            raise AssertionError(f"{runtime} audit should use AgentRuntimeAuditRunner")
        if not isinstance(
            create_exploit_runner(
                audit_result=audit_result,
                function_info=func_info,
                code_map=code_map,
                system_prompt="system",
                user_message="user",
                project_path=str(PROJECT_ROOT),
            ),
            AgentRuntimeExploitRunner,
        ):
            raise AssertionError(f"{runtime} exploit should use AgentRuntimeExploitRunner")

    configure_project_root(agent_runtime="deepagents")
    try:
        create_trace_explorer(FakeTraceAgent())
    except ValueError as exc:
        if "unsupported agent_runtime" not in str(exc):
            raise AssertionError(f"unexpected unsupported runtime error: {exc}")
    else:
        raise AssertionError("deepagents should no longer be a supported runtime")
    configure_project_root()


def verify_function_info_skill_runtime_installation() -> None:
    import tempfile

    func_info, _ = build_fake_audit_inputs()
    with tempfile.TemporaryDirectory() as tmpdir:
        for runtime in ("codex", "opencode", "claudecode"):
            installed = ensure_runtime_skill(
                func_info,
                runtime=runtime,
                project_path=tmpdir,
            )
            expected = Path(tmpdir).resolve() / runtime_skill_base_dir(runtime) / "civetweb_audit" / "SKILL.md"
            if not installed or installed.skill != "civetweb_audit":
                raise AssertionError("function skill should install for runtime")
            if installed.skill_file != expected:
                raise AssertionError(f"unexpected {runtime} skill path: {installed.skill_file}")
            if not expected.exists():
                raise AssertionError(f"{runtime} skill file should be copied into project")


def verify_prompts_reference_function_skill() -> None:
    import tempfile

    from agents.agent_runtime_runner import AgentRuntimeTraceExplorer
    from utils.runtime_skills import build_skill_usage_prompt

    func_info, _ = build_fake_audit_inputs()

    with tempfile.TemporaryDirectory() as tmpdir:
        trace_prompt = AgentRuntimeTraceExplorer(FakeTraceAgent(), runtime="codex")._system_prompt(
            func_info,
            project_path=tmpdir,
        )
        runtime_prompt = build_skill_usage_prompt(func_info, runtime="codex", project_path=tmpdir)
    if "civetweb_audit" not in trace_prompt:
        raise AssertionError("trace system prompt should mention FunctionInfo.skill")
    if ".agents/skills/civetweb_audit/SKILL.md" not in runtime_prompt:
        raise AssertionError("runtime skill prompt should include runtime-specific skill path")


def verify_exploit_prompt_references_function_skill() -> None:
    import tempfile

    import agents.agent_runtime_runner as runner_module
    from agents.agent_runtime_runner import AgentRuntimeExploitRunner

    func_info, code_map = build_fake_audit_inputs()
    audit_result = AuditResult(
        vulnerability_type="command_injection",
        is_vulnerable=True,
        confidence="high",
        description="fake vulnerable path",
        code_map=code_map,
    )
    captured: Dict[str, str] = {}

    class FakeRuntimeClient:
        def __init__(self, runtime: str, *, project_path: str, debug: bool = False):
            self.runtime = runtime
            self.project_path = project_path
            self.debug = debug

        def run_json(self, *, stage_name, system_prompt, user_prompt, output_model):
            captured["stage_name"] = stage_name
            captured["system_prompt"] = system_prompt
            return output_model(success=False, poc_command="", summary="fake"), []

    with tempfile.TemporaryDirectory() as tmpdir:
        original_client = runner_module.AgentRuntimeClient
        runner_module.AgentRuntimeClient = FakeRuntimeClient
        try:
            AgentRuntimeExploitRunner(
                runtime="codex",
                audit_result=audit_result,
                function_info=func_info,
                code_map=code_map,
                system_prompt="exploit system",
                user_message="exploit user",
                project_path=tmpdir,
            ).run()
        finally:
            runner_module.AgentRuntimeClient = original_client

    if captured.get("stage_name") != "exploit":
        raise AssertionError("exploit runner should call runtime exploit stage")
    if "civetweb_audit" not in captured.get("system_prompt", ""):
        raise AssertionError("exploit system prompt should mention FunctionInfo.skill")


def verify_civetweb_input_knowledge_moved_to_skill() -> None:
    scan_source = (PROJECT_ROOT / "scripts" / "scan.py").read_text(encoding="utf-8")
    skill_source = (
        PROJECT_ROOT / "skills" / "attack_surface" / "civetweb_audit" / "SKILL.md"
    ).read_text(encoding="utf-8")
    if "INPUT_POINT = \"\"\"" in scan_source or "CivetWeb 外部输入点说明" in scan_source:
        raise AssertionError("scripts/scan.py should not embed CivetWeb input knowledge")
    if "CivetWeb 外部输入点说明" not in skill_source or "mg_get_var" not in skill_source:
        raise AssertionError("civetweb audit skill should contain the external input knowledge")


def verify_agent_runtime_structured_output_parsing() -> None:
    parsed = extract_structured_model(
        {
            "info": {
                "structured_output": {
                    "function_info": fake_function_info_dict(),
                    "code_logic": "parsed from agent runtime",
                    "code_map": [
                        {
                            "function_name": "handle_test",
                            "file_path": "src/test.c",
                            "line_start": 1,
                            "line_end": 2,
                            "code_snippet": "int handle_test() {}",
                            "is_entry_point": True,
                        }
                    ],
                }
            }
        },
        TraceOutput,
    )
    if parsed.code_logic != "parsed from agent runtime":
        raise AssertionError("agent runtime structured_output should parse")


def verify_agent_runtime_uses_strict_json_schema() -> None:
    from agents.runtime_clients import AgentRuntimeClient, CodexRuntimeClient

    client = AgentRuntimeClient("codex", project_path=str(PROJECT_ROOT))
    if not isinstance(client.provider, CodexRuntimeClient):
        raise AssertionError("codex facade should select CodexRuntimeClient")
    schema = client._output_schema(AuditOutput)
    if schema.get("additionalProperties") is not False:
        raise AssertionError("agent runtime schema root must set additionalProperties=false")

    properties = schema.get("properties") or {}
    if set(schema.get("required") or []) != set(properties):
        raise AssertionError("agent runtime schema should require every root property")

    code_context_schema = (schema.get("$defs") or {}).get("CodeContext") or {}
    if code_context_schema.get("additionalProperties") is not False:
        raise AssertionError("agent runtime schema defs must set additionalProperties=false")


def verify_agent_runtime_invalid_command_fallback() -> None:
    from agents.runtime_clients.codex import CodexRuntimeClient

    client = CodexRuntimeClient(project_path=str(PROJECT_ROOT))
    try:
        client._run_command(["codex\0exec", "--version"], get_config())
    except RuntimeError as exc:
        if "contains NUL byte" not in str(exc):
            raise AssertionError(f"unexpected invalid command error: {exc}")
    else:
        raise AssertionError("agent runtime command containing NUL should fail with RuntimeError")


def verify_codex_command_builder_uses_exec_mode() -> None:
    from agents.runtime_clients.codex import CodexRuntimeClient

    configure_project_root()
    client = CodexRuntimeClient(project_path=str(PROJECT_ROOT))
    command = client.build_command("/tmp/schema.json", output_path="/tmp/last.json")
    if command[:2] != ["codex", "exec"]:
        raise AssertionError(f"codex runtime should use exec mode, got: {command[:2]}")
    if "--non-interactive" in command or "--ask-for-approval" in command:
        raise AssertionError("codex runtime should not use removed or unsupported flags")
    if "-c" not in command or 'approval_policy="never"' not in command:
        raise AssertionError("codex runtime should disable approvals via config override")
    if "--output-schema" not in command or "--output-last-message" not in command:
        raise AssertionError("codex runtime should pass output schema and last-message file")


def verify_audit_agent_uses_specs_and_agent_runtime_runner() -> None:
    from dataclasses import fields
    import agents.agent_runtime_runner as agent_runtime_runner
    from agents.audit_agent import AuditAgent
    from agents.audit_specs import AUDIT_SPECS, AuditSpec

    configure_project_root(agent_runtime="codex")
    func_info, code_map = build_fake_audit_inputs()
    expected_types = ["command_injection", "path_traversal", "brute_force", "password_reset", "loop"]
    calls: List[Dict] = []

    def fake_run(self):
        calls.append({
            "agent_name": self.agent_name,
            "vulnerability_type": self.vulnerability_type,
            "runtime": self.runtime,
        })
        return AuditResult(
            vulnerability_type=self.vulnerability_type,
            is_vulnerable=False,
            confidence="low",
            description=f"fake {self.vulnerability_type}",
            code_map=self.code_map,
        )

    original_run = agent_runtime_runner.AgentRuntimeAuditRunner.run
    agent_runtime_runner.AgentRuntimeAuditRunner.run = fake_run
    try:
        audit_agent = AuditAgent(func_info, code_map, project_path=str(PROJECT_ROOT))
        results, exploit_results = audit_agent.audit()
    finally:
        agent_runtime_runner.AgentRuntimeAuditRunner.run = original_run

    if set(AUDIT_SPECS) != set(expected_types):
        raise AssertionError("audit specs should define the expected vulnerability types")
    if not all(getattr(spec, "source_path", None) for spec in AUDIT_SPECS.values()):
        raise AssertionError("audit specs should be loaded from YAML files")
    spec_field_names = {field.name for field in fields(AuditSpec)}
    removed_fields = {
        "agent_name",
        "display_name",
        "build_system_prompt",
        "enable_exploit",
        "enabled_by_default",
        "severity",
        "category",
        "cwe",
        "exploit_confidence",
    }
    present_removed_fields = removed_fields.intersection(spec_field_names)
    if present_removed_fields:
        raise AssertionError(f"AuditSpec should not expose removed YAML contract fields: {sorted(present_removed_fields)}")
    for spec_path in PROJECT_ROOT.glob("audit_specs/*.yaml"):
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if set(data) != {"name", "user_prompt"}:
            raise AssertionError(f"{spec_path} should contain only name and user_prompt, got {sorted(data)}")
    if [result.vulnerability_type for result in results] != expected_types:
        raise AssertionError("AuditAgent did not return expected vulnerability types")
    if [call["agent_name"] for call in calls] != [f"{audit_type}_audit" for audit_type in expected_types]:
        raise AssertionError("AuditAgent should generate runner agent_name from audit_type")
    if [call["runtime"] for call in calls] != ["codex"] * len(expected_types):
        raise AssertionError("AuditAgent specs should delegate to the configured agent runtime")
    if exploit_results:
        raise AssertionError("low-confidence fake results should not trigger exploit")


def verify_audit_common_system_prompt_owns_codemap() -> None:
    import tempfile

    from agents.agent_runtime_runner import AgentRuntimeAuditRunner
    from agents.audit_specs import AUDIT_SPECS

    configure_project_root(agent_runtime="codex")
    func_info, code_map = build_fake_audit_inputs()
    spec = AUDIT_SPECS["command_injection"]
    user_message = spec.build_user_message(func_info, code_map)
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = AgentRuntimeAuditRunner(
            runtime="codex",
            agent_name=spec.agent_name,
            vulnerability_type=spec.audit_type,
            function_info=func_info,
            code_map=code_map,
            system_prompt=spec.build_system_prompt(func_info, code_map),
            user_message=user_message,
            project_path=tmpdir,
        )
        system_prompt = runner._system_prompt()
    if "## Common Audit Context" not in system_prompt:
        raise AssertionError("audit runner should build a common system prompt")
    if "handle_test" not in system_prompt or '"function_name": "handle_test"' not in system_prompt:
        raise AssertionError("common system prompt should include func_name and code_map JSON")
    if "```json" in user_message or '"function_name"' in user_message:
        raise AssertionError("vulnerability user prompt should not inject code_map JSON")


def verify_field_injection_is_system_only() -> None:
    import tempfile

    from agents.agent_runtime_runner import AgentRuntimeAuditRunner, AgentRuntimeTraceExplorer
    from agents.audit_specs import AUDIT_SPECS
    from agents.output_schemas import AuditOutput
    from agents.runtime_clients.codex import CodexRuntimeClient

    func_info, code_map = build_fake_audit_inputs()
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_runner = AgentRuntimeTraceExplorer(FakeTraceAgent(), runtime="codex")
        trace_system = trace_runner._system_prompt(func_info, project_path=tmpdir)
        trace_user = trace_runner._user_prompt()
        if "handle_test" not in trace_system or "int handle_test()" not in trace_system:
            raise AssertionError("trace system prompt should contain FunctionInfo fields")
        if "handle_test" in trace_user or "int handle_test()" in trace_user:
            raise AssertionError("trace user prompt should not contain FunctionInfo fields")

        spec = AUDIT_SPECS["command_injection"]
        runner = AgentRuntimeAuditRunner(
            runtime="codex",
            agent_name=spec.agent_name,
            vulnerability_type=spec.audit_type,
            function_info=func_info,
            code_map=code_map,
            system_prompt=spec.build_system_prompt(func_info, code_map),
            user_message=spec.build_user_message(func_info, code_map),
            project_path=tmpdir,
        )
        audit_system = runner._system_prompt()
        audit_user = runner._user_prompt()
        if "## Unified System Prompt" not in audit_system or '"function_name": "handle_test"' not in audit_system:
            raise AssertionError("audit system prompt should own all injected fields")
        if "handle_test" in audit_user or '"function_name"' in audit_user:
            raise AssertionError("audit user prompt should not contain injected fields")

        client = CodexRuntimeClient(project_path=tmpdir)
        full_prompt = client._build_prompt(
            "command_injection_audit",
            audit_system,
            audit_user,
            AuditOutput,
        )
    system_part, user_part = full_prompt.split("## User Task", 1)
    if "## JSON Schema" not in system_part or "工作目录已绑定" not in system_part:
        raise AssertionError("runtime and schema fields should be in the unified system prompt")
    if "handle_test" in user_part or '"function_name"' in user_part or "JSON Schema" in user_part:
        raise AssertionError("user task section should not contain injected fields")


def verify_specialized_audit_agents_removed() -> None:
    forbidden_paths = [
        PROJECT_ROOT / "agents" / "brute_force_agent.py",
        PROJECT_ROOT / "agents" / "command_inject_agent.py",
        PROJECT_ROOT / "agents" / "loop_vulnerability_agent.py",
        PROJECT_ROOT / "agents" / "password_reset_agent.py",
        PROJECT_ROOT / "agents" / "path_traversal_agent.py",
    ]
    existing = [str(path.relative_to(PROJECT_ROOT)) for path in forbidden_paths if path.exists()]
    if existing:
        raise AssertionError(f"specialized audit agent files should be removed: {existing}")


def verify_deepagents_removed() -> None:
    forbidden_paths = [
        PROJECT_ROOT / "agents" / "deepagents_trace_explorer.py",
        PROJECT_ROOT / "agents" / "deepagents_audit_runner.py",
        PROJECT_ROOT / "agents" / "deepagents_exploit_runner.py",
        PROJECT_ROOT / "utils" / "deepagents_runtime.py",
        PROJECT_ROOT / "utils" / "logged_backend.py",
    ]
    existing = [str(path.relative_to(PROJECT_ROOT)) for path in forbidden_paths if path.exists()]
    if existing:
        raise AssertionError(f"deepagents files should be removed: {existing}")

    source_files = [
        PROJECT_ROOT / "agents" / "runtime_factory.py",
        PROJECT_ROOT / "config.py",
        PROJECT_ROOT / "cli.py",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / "pyproject.toml",
    ]
    for path in source_files:
        text = path.read_text(encoding="utf-8")
        if "deepagents" in text.lower():
            raise AssertionError(f"{path.relative_to(PROJECT_ROOT)} should not reference deepagents")

    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if "deepagents" in pyproject:
        raise AssertionError("pyproject should not depend on deepagents")


def verify_legacy_tool_registry_removed() -> None:
    forbidden_paths = [
        PROJECT_ROOT / "tools" / "executor.py",
        PROJECT_ROOT / "tools" / "registry.py",
        PROJECT_ROOT / "tools" / "file_tool.py",
        PROJECT_ROOT / "tools" / "skills_tool.py",
        PROJECT_ROOT / "tools" / "agent_tool.py",
    ]
    existing = [str(path.relative_to(PROJECT_ROOT)) for path in forbidden_paths if path.exists()]
    if existing:
        raise AssertionError(f"legacy tool registry files should be removed: {existing}")

    from tools import TagsTool, find_refs, go_to_def

    if not callable(go_to_def) or not callable(find_refs):
        raise AssertionError("tags helpers should remain callable")
    if not hasattr(TagsTool, "execute"):
        raise AssertionError("TagsTool should remain available")
    if not hasattr(TagsTool(), "_go_to_def") or not hasattr(TagsTool(), "_find_refs"):
        raise AssertionError("TagsTool methods should be bound to the class")
    missing_index = go_to_def("DefinitelyMissingSymbol")
    if "索引不存在" not in missing_index and "未找到符号" not in missing_index:
        raise AssertionError(f"tags helper returned unexpected output: {missing_index}")


def verify_tags_mcp_server() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run_check() -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "tools.tags_mcp_server",
                "--project-path",
                str(PROJECT_ROOT),
            ],
            cwd=PROJECT_ROOT,
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = sorted(tool.name for tool in tools.tools)
                if names != ["find_refs", "go_to_def"]:
                    raise AssertionError(f"unexpected tags MCP tools: {names}")

                result = await session.call_tool(
                    "go_to_def",
                    {"symbol": "DefinitelyMissingSymbol"},
                )
                text = result.content[0].text if result.content else ""
                if "索引不存在" not in text and "未找到符号" not in text:
                    raise AssertionError(f"unexpected tags MCP result: {text}")

    asyncio.run(run_check())


def verify_runtime_config_removed_legacy_llm_fields() -> None:
    config = get_config()
    forbidden_fields = {
        "base_url",
        "api_key",
        "model_name",
        "deepseek_thinking",
        "deepseek_reasoning_effort",
        "codex_command",
        "claudecode_command",
        "enable_lsp",
        "max_turns",
        "max_tool_calls",
        "max_repeated_tool_calls",
        "exploit_backend",
        "opensandbox_image",
        "opensandbox_project_dir",
        "opensandbox_timeout_seconds",
        "opensandbox_ready_timeout_seconds",
        "opensandbox_upload_max_file_mb",
        "opensandbox_upload_excludes",
        "skills_path",
    }
    present = forbidden_fields.intersection(config.model_dump().keys())
    if present:
        raise AssertionError(f"legacy LLM config fields should be removed: {sorted(present)}")

    if (PROJECT_ROOT / "utils" / "llm_client.py").exists():
        raise AssertionError("legacy utils/llm_client.py should be removed")
    if (PROJECT_ROOT / "utils" / "tool_call_guard.py").exists():
        raise AssertionError("unused utils/tool_call_guard.py should be removed")
    if (PROJECT_ROOT / "utils" / "tool_call_logger.py").exists():
        raise AssertionError("unused utils/tool_call_logger.py should be removed")


def verify_opencode_runtime_uses_current_api_and_reports_bad_json() -> None:
    from agents.runtime_clients.opencode import OpenCodeRuntimeClient
    from utils.structured_output import extract_structured_model

    class FakeConfig:
        opencode_base_url = "http://127.0.0.1:4096"
        opencode_provider_id = ""
        opencode_model_id = ""
        opencode_enable_event_stream = False
        opencode_structured_output_mode = "prompt"
        external_runtime_timeout_seconds = 1

    class FakeOpenCodeRuntimeClient(OpenCodeRuntimeClient):
        def __init__(self):
            super().__init__(project_path=str(PROJECT_ROOT), debug=False)
            self.paths: list[str] = []
            self.bodies: list[dict] = []
            self.logs: list[str] = []

        def _start_activity_listeners(self, session_id, *, stage_name, config):
            class NoopStop:
                def set(self):
                    pass

            return NoopStop()

        def _log(self, message):
            self.logs.append(message)

        def _request(self, method, path, body, config):
            self.paths.append(path)
            if isinstance(body, dict):
                self.bodies.append(body)
            if path == "/session":
                return {"id": "ses_test"}
            if path == "/session/ses_test/message":
                return {"ok": True}
            if path == "/permission/per_test/reply":
                return True
            raise AssertionError(f"unexpected opencode path: {path}")

        def _ask_permission_reply(self, request, *, session_id):
            self.logs.append(f"asked permission {request['id']} for {session_id}")
            return "once"

    client = FakeOpenCodeRuntimeClient()
    result = client.run_raw(
        prompt="hello",
        output_model=TraceOutput,
        config=FakeConfig(),
        stage_name="trace",
    )
    if result != {"ok": True}:
        raise AssertionError("opencode runtime should return prompt response")
    if client.paths != ["/session", "/session/ses_test/message"]:
        raise AssertionError(f"opencode runtime should use current API paths, got {client.paths}")
    if "format" in client.bodies[-1]:
        raise AssertionError("opencode prompt fallback mode should not send format=json_schema")
    tools = client.bodies[-1].get("tools") or {}
    if tools.get("bash") is not True or tools.get("shell") is not True:
        raise AssertionError("opencode runtime should allow bash/shell by default")
    if any(tool in tools for tool in ("write", "edit", "patch", "multiedit")):
        raise AssertionError("opencode runtime should leave write/edit/patch to default permission prompts")

    try:
        client._parse_json_response(
            "<!doctype html>",
            base_url="http://127.0.0.1:4096",
            path="/session/create",
            status=200,
        )
    except RuntimeError as exc:
        if "non-JSON response" not in str(exc):
            raise AssertionError(f"unexpected opencode bad JSON error: {exc}")
    else:
        raise AssertionError("opencode non-JSON responses should raise a diagnostic RuntimeError")

    extracted = extract_structured_model(
        {
            "info": {
                "role": "assistant",
                "structured": {
                    "function_info": fake_function_info_dict(),
                    "code_logic": "ok",
                    "code_map": [],
                },
            },
            "parts": [],
        },
        TraceOutput,
    )
    if extracted.code_logic != "ok":
        raise AssertionError("structured output extractor should read opencode info.structured")

    extracted_from_text = extract_structured_model(
        {
            "info": {"role": "assistant"},
            "parts": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "function_info": fake_function_info_dict(),
                            "code_logic": "from text",
                            "code_map": [],
                        }
                    ),
                }
            ],
        },
        TraceOutput,
    )
    if extracted_from_text.code_logic != "from text":
        raise AssertionError("structured output extractor should read opencode text parts")

    try:
        client._raise_for_assistant_error(
            {
                "info": {
                    "error": {
                        "name": "APIError",
                        "data": {"message": "provider failed", "responseBody": "bad"},
                    }
                }
            }
        )
    except RuntimeError as exc:
        if "provider failed" not in str(exc):
            raise AssertionError(f"unexpected opencode assistant error: {exc}")
    else:
        raise AssertionError("opencode assistant errors should be raised explicitly")

    client._log_tool_parts(
        {
            "type": "message.updated",
            "properties": {
                "part": {
                    "type": "tool",
                    "sessionID": "ses_test",
                    "messageID": "msg_test",
                    "callID": "call_test",
                    "tool": "read",
                    "state": {
                        "status": "completed",
                        "input": {"filePath": "README.md"},
                        "output": "ok",
                        "title": "Read README",
                        "metadata": {},
                        "time": {"start": 1, "end": 2},
                    },
                }
            },
        },
        session_id="ses_test",
    )
    if not any("[opencode:tool]" in message and "tool=read" in message for message in client.logs):
        raise AssertionError("opencode event listener should log tool parts")

    client._handle_permission_event(
        {
            "type": "permission.asked",
            "properties": {
                "id": "per_test",
                "sessionID": "ses_test",
                "permission": "tool.write",
                "patterns": ["**/*.md"],
                "metadata": {"action": "write README.md"},
                "always": [],
                "tool": {"messageID": "msg_test", "callID": "call_write"},
            },
        },
        session_id="ses_test",
        config=FakeConfig(),
        seen_permissions=set(),
    )
    if "/permission/per_test/reply" not in client.paths:
        raise AssertionError("opencode permission requests should be replied through permission API")
    if client.bodies[-1].get("reply") != "once":
        raise AssertionError("opencode permission reply should use once/always/reject contract")

    contextual_path = client._path_with_project_context("/session/ses_test/message")
    directory = (parse_qs(urlsplit(contextual_path).query).get("directory") or [""])[0]
    if not directory:
        raise AssertionError("opencode runtime should bind requests to project directory")
    if directory != str(PROJECT_ROOT.resolve()):
        raise AssertionError(f"opencode directory query should use resolved project path: {contextual_path}")


def verify_opencode_structured_output_probe_and_modes() -> None:
    from agents.runtime_clients.opencode import OpenCodeRuntimeClient

    class FakeConfig:
        opencode_base_url = "http://127.0.0.1:4096"
        opencode_provider_id = "deepseek"
        opencode_model_id = "deepseek-v4-pro"
        opencode_enable_event_stream = False
        opencode_structured_output_mode = "json_schema"
        external_runtime_timeout_seconds = 1

    class FakeAutoConfig(FakeConfig):
        opencode_structured_output_mode = "auto"

    class FakeOpenCodeRuntimeClient(OpenCodeRuntimeClient):
        def __init__(self, outcomes):
            super().__init__(project_path=str(PROJECT_ROOT), debug=False)
            self.outcomes = list(outcomes)
            self.paths: list[str] = []
            self.bodies: list[dict] = []
            self.logs: list[str] = []

        def _start_activity_listeners(self, session_id, *, stage_name, config):
            class NoopStop:
                def set(self):
                    pass

            return NoopStop()

        def _log(self, message):
            self.logs.append(message)

        def _request(self, method, path, body, config):
            self.paths.append(path)
            if isinstance(body, dict):
                self.bodies.append(body)
            if path == "/session":
                return {"id": f"ses_{len(self.paths)}"}
            if path.startswith("/session/") and path.endswith("/message"):
                outcome = self.outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            raise AssertionError(f"unexpected opencode path: {path}")

    client = FakeOpenCodeRuntimeClient([{"info": {"structured": {"ok": True}}, "parts": []}])
    result = client.run_raw(
        prompt="hello",
        output_model=TraceOutput,
        config=FakeConfig(),
        stage_name="trace",
    )
    if result["info"]["structured"]["ok"] is not True:
        raise AssertionError("opencode runtime should return structured response")
    if client.bodies[-1].get("format", {}).get("type") != "json_schema":
        raise AssertionError("opencode json_schema mode should send format=json_schema")
    if "function_info" not in client.bodies[-1]["format"]["schema"].get("properties", {}):
        raise AssertionError("opencode json_schema mode should send the requested output model schema")

    discovery_client = FakeOpenCodeRuntimeClient([{"info": {"structured": {"functions": []}}, "parts": []}])
    discovery_client.run_raw(
        prompt="discover",
        output_model=EntryDiscoveryOutput,
        config=FakeConfig(),
        stage_name="entry_discovery",
    )
    discovery_schema = discovery_client.bodies[-1]["format"]["schema"]
    schema_text = json.dumps(discovery_schema, ensure_ascii=False)
    for rejected_key in ("$defs", "$ref", "anyOf", "description", "title", "additionalProperties", "default"):
        if rejected_key in schema_text:
            raise AssertionError(f"opencode json_schema mode should remove {rejected_key} before sending format schema")
    item_schema = discovery_schema["properties"]["functions"]["items"]
    if item_schema.get("properties", {}).get("start_line", {}).get("type") != "integer":
        raise AssertionError("opencode schema sanitizer should keep start_line as an integer field")

    probe_client = FakeOpenCodeRuntimeClient(
        [
            RuntimeError("deepseek-reasoner does not support this tool_choice"),
        ]
    )
    decision = probe_client.probe_structured_output(FakeAutoConfig())
    if decision.mode != "prompt":
        raise AssertionError(f"probe should fall back to prompt mode without changing thinking/variant, got {decision}")
    if probe_client.bodies[0].get("format", {}).get("type") != "json_schema":
        raise AssertionError("probe should try json_schema first")
    if len(probe_client.bodies) != 1:
        raise AssertionError("probe should not retry with no-thinking variants; users own thinking mode")

    class PollProbeClient(FakeOpenCodeRuntimeClient):
        def _handle_pending_permissions(self, *_args, **_kwargs):
            pass

    class StopAfterPermissionConfig(FakeConfig):
        external_runtime_timeout_seconds = 1

    poll_client = PollProbeClient([])
    stop_event = __import__("threading").Event()

    def request_once(method, path, body, config):
        poll_client.paths.append(path)
        stop_event.set()
        if path == "/permission":
            return []
        raise AssertionError(f"json_schema polling should not request {path}")

    poll_client._request = request_once
    poll_client._poll_session_messages(
        "ses_test",
        "entry_discovery",
        StopAfterPermissionConfig(),
        stop_event,
        set(),
        set(),
    )
    if "/session/ses_test/message" in poll_client.paths:
        raise AssertionError("opencode json_schema mode should skip broken message-list polling")
    if "/permission" not in poll_client.paths:
        raise AssertionError("opencode json_schema mode should still poll permissions")

    fallback_client = FakeOpenCodeRuntimeClient(
        [
            RuntimeError("tool_choice unsupported"),
        ]
    )
    fallback = fallback_client.probe_structured_output(FakeAutoConfig())
    if fallback.mode != "prompt":
        raise AssertionError(f"fully unsupported probe should fall back to prompt mode, got {fallback}")

    schema_reject_client = FakeOpenCodeRuntimeClient(
        [RuntimeError("opencode serve returned HTTP 400: Expected OutputFormatJsonSchema")]
    )
    try:
        schema_reject_client.run_raw(
            prompt="discover",
            output_model=EntryDiscoveryOutput,
            config=FakeConfig(),
            stage_name="entry_discovery",
        )
    except RuntimeError as exc:
        if "Expected OutputFormatJsonSchema" not in str(exc):
            raise AssertionError(f"unexpected schema rejection error: {exc}")
    else:
        raise AssertionError("opencode schema rejection should not silently downgrade")
    if len(schema_reject_client.bodies) != 1 or "format" not in schema_reject_client.bodies[0]:
        raise AssertionError("opencode schema rejection should preserve the original json_schema attempt")
    import tempfile
    import urllib.error

    with tempfile.TemporaryDirectory() as tmpdir:
        class FakePollConfig(FakeConfig):
            output_dir = tmpdir

        cause = urllib.error.HTTPError(
            url="http://127.0.0.1:4096/session/test/message",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=None,
        )
        full_body = "Expected OutputFormatJsonSchema " + ("x" * 1200)
        setattr(cause, "_tsj_response_body", full_body)
        error = RuntimeError("opencode serve returned HTTP 400: Expected OutputFormatJsonSchema ...")
        error.__cause__ = cause
        detail_path = client._write_poll_error_detail(
            stage_name="entry_discovery",
            session_id="ses_test",
            exc=error,
            config=FakePollConfig(),
        )
        if detail_path is None or not detail_path.exists():
            raise AssertionError("opencode poll format errors should be written to a detail log")
        detail_content = detail_path.read_text(encoding="utf-8")
        if full_body not in detail_content:
            raise AssertionError("opencode poll detail log should contain the full error text")


def main() -> None:
    configure_project_root()
    verify_trace_agent_pipeline()
    verify_trace_runtime_valueerror_falls_back()
    verify_agent_runtime_factory_returns_runtime_runners()
    verify_function_info_skill_runtime_installation()
    verify_prompts_reference_function_skill()
    verify_exploit_prompt_references_function_skill()
    verify_civetweb_input_knowledge_moved_to_skill()
    verify_agent_runtime_structured_output_parsing()
    verify_agent_runtime_uses_strict_json_schema()
    verify_agent_runtime_invalid_command_fallback()
    verify_codex_command_builder_uses_exec_mode()
    verify_audit_agent_uses_specs_and_agent_runtime_runner()
    verify_audit_common_system_prompt_owns_codemap()
    verify_field_injection_is_system_only()
    verify_specialized_audit_agents_removed()
    verify_deepagents_removed()
    verify_legacy_tool_registry_removed()
    verify_tags_mcp_server()
    verify_runtime_config_removed_legacy_llm_fields()
    verify_opencode_runtime_uses_current_api_and_reports_bad_json()
    verify_opencode_structured_output_probe_and_modes()
    print("Agent runtime migration verification passed")


if __name__ == "__main__":
    main()
