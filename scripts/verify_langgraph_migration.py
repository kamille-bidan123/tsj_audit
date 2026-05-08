#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the LangGraph trace workflow without calling a real LLM."""

from __future__ import annotations

import sys
import tempfile
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

import tools  # noqa: F401 - importing registers tool classes
from agents.deepagents_trace_explorer import DeepAgentsTraceExplorer, DeepTraceOutput
import agents.trace_workflow as trace_workflow
from agents.prompt import build_exploration_user_message
from agents.trace_workflow import TraceWorkflow
from config import init_settings
from models import AuditResult, CodeContext, FunctionInfo
from models import ExploitResult
from tools.registry import ToolRegistry

PROJECT_ROOT = Path(__file__).parent.parent


def configure_project_root() -> None:
    """Keep verification independent from local .env project_path values."""
    init_settings({
        "api_key": "verification-only",
        "base_url": "http://127.0.0.1:9/v1",
        "model_name": "fake-model",
        "project_path": str(PROJECT_ROOT),
        "skills_path": str(PROJECT_ROOT / "skills"),
        "exploit_backend": "filesystem",
        "target_base_url": "http://example.test",
        "deepseek_thinking": "disabled",
        "deepseek_reasoning_effort": "",
    })


class FakeTraceAgent:
    """Small test double for the TraceAgent methods used by TraceWorkflow."""

    def __init__(self):
        self.saved_conversations: List[tuple[str, str, List[Dict]]] = []

    def _audit_codemap(
        self,
        func_info: FunctionInfo,
        code_map: List[CodeContext],
    ):
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

    def _save_conversation_history(
        self,
        agent_name: str,
        func_info: FunctionInfo,
        messages: List[Dict],
    ) -> None:
        self.saved_conversations.append((agent_name, func_info.func_name, messages))


def verify_legacy_tool_registry() -> None:
    """Trace exploration keeps only non-file project tools from the legacy registry."""
    expected_commands = {
        "go_to_def",
        "find_refs",
        "skill",
    }
    commands = set(ToolRegistry.get_all_commands())
    missing = expected_commands - commands
    if missing:
        raise AssertionError(f"missing registered tools: {sorted(missing)}")

    schema = ToolRegistry.to_openai_tools(["go_to_def", "find_refs", "skill"])
    schema_names = {item["function"]["name"] for item in schema}
    if schema_names != {"go_to_def", "find_refs", "skill"}:
        raise AssertionError(f"unexpected schema names: {sorted(schema_names)}")

    deepagents_tool_names = {tool.__name__ for tool in DeepAgentsTraceExplorer.TOOLS}
    expected_deepagents_tools = {"project_go_to_def", "project_find_refs", "project_skill"}
    if deepagents_tool_names != expected_deepagents_tools:
        raise AssertionError(f"unexpected DeepAgents tools: {sorted(deepagents_tool_names)}")


def verify_deepagents_filesystem_backend() -> None:
    """DeepAgents filesystem should be bound to config.project_path and replace filetool."""
    from utils.logged_backend import LoggedBackend

    explorer = DeepAgentsTraceExplorer(FakeTraceAgent())
    explorer.audit_function_name = "handle_test"
    backend = explorer._build_backend()
    if not isinstance(backend, LoggedBackend):
        raise AssertionError("DeepAgents filesystem backend should be wrapped with LoggedBackend")

    read_result = backend.read("/pyproject.toml", limit=3)
    if read_result.error:
        raise AssertionError(f"DeepAgents read_file returned error: {read_result.error}")
    content = read_result.file_data["content"]
    if "[project]" not in content or 'name = "tsj-audit"' not in content:
        raise AssertionError("DeepAgents read_file did not read project pyproject.toml")

    ls_result = backend.ls("/")
    if ls_result.error:
        raise AssertionError(f"DeepAgents ls returned error: {ls_result.error}")
    if not any(item["path"] == "/pyproject.toml" for item in ls_result.entries):
        raise AssertionError("DeepAgents ls did not list project root files")

    grep_result = backend.grep('name = "tsj-audit"', path="/", glob="*.toml")
    if grep_result.error:
        raise AssertionError(f"DeepAgents grep returned error: {grep_result.error}")
    if not any(match["path"] == "/pyproject.toml" for match in grep_result.matches):
        raise AssertionError("DeepAgents grep did not search inside project root")

    permissions = explorer._filesystem_permissions()
    if not any(
        permission.mode == "deny"
        and "write" in permission.operations
        and "/**" in permission.paths
        for permission in permissions
    ):
        raise AssertionError("DeepAgents filesystem is missing write-deny permission")


def verify_logged_backend_summaries() -> None:
    from deepagents.backends import FilesystemBackend
    from utils.logged_backend import LoggedBackend

    backend = LoggedBackend(
        FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
        audit_function_name="handle_test",
    )
    ls_result = backend.ls("/")
    read_result = backend.read("/pyproject.toml", limit=3)
    grep_result = backend.grep('name = "tsj-audit"', path="/", glob="*.toml")
    glob_result = backend.glob("*.toml", path="/")

    if ls_result.error or not ls_result.entries:
        raise AssertionError("LoggedBackend ls should delegate to wrapped backend")
    if read_result.error or "[project]" not in read_result.file_data["content"]:
        raise AssertionError("LoggedBackend read should delegate to wrapped backend")
    if grep_result.error or not grep_result.matches:
        raise AssertionError("LoggedBackend grep should delegate to wrapped backend")
    if glob_result.error or not glob_result.matches:
        raise AssertionError("LoggedBackend glob should delegate to wrapped backend")


def verify_logged_backend_duplicate_and_budget_guards() -> None:
    from deepagents.backends import FilesystemBackend
    from utils.logged_backend import LoggedBackend

    backend = LoggedBackend(
        FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
        prefix="guard_fs",
        audit_function_name="handle_test",
        max_tool_calls=3,
        max_repeated_calls=1,
        blocked_grep_patterns={"system"},
    )

    first = backend.read("/pyproject.toml", limit=1)
    duplicate = backend.read("/pyproject.toml", limit=1)
    blocked = backend.grep("system", path="/pyproject.toml", glob="*.toml")
    over_budget = backend.ls("/")

    if first.error:
        raise AssertionError("first guarded backend call should pass")
    if duplicate.error is None or "重复工具调用" not in duplicate.error:
        raise AssertionError("duplicate backend call should be short-circuited")
    if blocked.error is None or "禁止搜索危险函数" not in blocked.error:
        raise AssertionError("dangerous grep pattern should be blocked")
    if over_budget.error is None or "工具调用上限" not in over_budget.error:
        raise AssertionError("backend should enforce max_tool_calls")


def verify_project_tools_share_tool_call_guards() -> None:
    from tools.executor import ToolExecutor
    from utils.tool_call_guard import ToolCallGuard

    budget_guard = ToolCallGuard(max_tool_calls=1, max_repeated_calls=10)
    first = ToolExecutor.call(
        "go_to_def",
        {"symbol": "DefinitelyMissingSymbol"},
        audit_function_name="handle_test",
        tool_guard=budget_guard,
    )
    over_budget = ToolExecutor.call(
        "find_refs",
        {"symbol": "DefinitelyMissingSymbol"},
        audit_function_name="handle_test",
        tool_guard=budget_guard,
    )

    if "工具调用上限" in first or "重复工具调用" in first:
        raise AssertionError("first guarded project tool call should execute normally")
    if "工具调用上限" not in over_budget:
        raise AssertionError("project tools should enforce the shared tool-call budget")

    duplicate_guard = ToolCallGuard(max_tool_calls=10, max_repeated_calls=1)
    ToolExecutor.call(
        "go_to_def",
        {"symbol": "DefinitelyMissingSymbol"},
        audit_function_name="handle_test",
        tool_guard=duplicate_guard,
    )
    duplicate = ToolExecutor.call(
        "go_to_def",
        {"symbol": "DefinitelyMissingSymbol"},
        audit_function_name="handle_test",
        tool_guard=duplicate_guard,
    )
    if "重复工具调用" not in duplicate:
        raise AssertionError("project tools should enforce duplicate-call limits")


def verify_tool_logs_include_audit_function_name() -> None:
    from deepagents.backends import FilesystemBackend
    from tools.executor import ToolExecutor
    from utils.logged_backend import LoggedBackend
    from utils.tool_call_logger import ToolCallLogger

    capture = StringIO()
    with redirect_stdout(capture):
        ToolExecutor.call(
            "go_to_def",
            {"symbol": "DefinitelyMissingSymbol"},
            audit_function_name="handle_test",
        )
        LoggedBackend(
            FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True),
            audit_function_name="handle_test",
        ).read("/pyproject.toml", limit=1)

    output = capture.getvalue()
    if "[handle_test] [tool#" not in output:
        raise AssertionError("tool logs should prefix call ids with the audited function name")
    if "[tool#" in output.replace("[handle_test] [tool#", ""):
        raise AssertionError("all tool call id logs should include the audited function name prefix")

    capture = StringIO()
    with redirect_stdout(capture):
        call_id = ToolCallLogger.start("verification_tool", {"input": "x"}, audit_function_name="handle_test")
        ToolCallLogger.end(call_id, "verification_tool", "secret return value", audit_function_name="handle_test")
    output = capture.getvalue()
    if "secret return value" in output or "ret:" in output:
        raise AssertionError("tool return values should be hidden when debug is disabled")

    capture = StringIO()
    with redirect_stdout(capture):
        call_id = ToolCallLogger.start(
            "verification_tool",
            {"input": "x"},
            audit_function_name="handle_test",
            debug=True,
        )
        ToolCallLogger.end(
            call_id,
            "verification_tool",
            "visible return value",
            audit_function_name="handle_test",
            debug=True,
        )
    output = capture.getvalue()
    if "visible return value" not in output or "ret:" not in output:
        raise AssertionError("tool return values should be visible when debug is enabled")


def verify_workflow() -> None:
    func_info = FunctionInfo(
        func_name="handle_test",
        file_path="src/test.c",
        start_line=10,
        end_line=20,
        code_snippet="int handle_test() { return 0; }",
        input="mg_get_var",
        audit_types=["command_injection"],
    )

    def fake_deepagents_run(self, func_info: FunctionInfo):
        return (
            "fake code logic",
            [
                CodeContext(
                    function_name=func_info.func_name,
                    file_path=func_info.file_path,
                    line_start=func_info.start_line,
                    line_end=func_info.end_line,
                    code_snippet=func_info.code_snippet,
                    is_entry_point=True,
                    taint_source=func_info.input,
                    taint_path="fake source -> fake sink",
                )
            ],
            [{"role": "assistant", "content": "fake-codemap"}],
        )

    original_run = trace_workflow.DeepAgentsTraceExplorer.run
    trace_workflow.DeepAgentsTraceExplorer.run = fake_deepagents_run
    try:
        fake_agent = FakeTraceAgent()
        result = TraceWorkflow(fake_agent).run(func_info)
    finally:
        trace_workflow.DeepAgentsTraceExplorer.run = original_run

    assert result.function_info.func_name == "handle_test"
    assert result.code_logic == "fake code logic"
    assert len(result.code_map) == 1
    assert len(result.audit_results) == 1
    assert result.audit_results[0].vulnerability_type == "command_injection"
    assert fake_agent.saved_conversations


def verify_deepagents_adapter() -> None:
    explorer = DeepAgentsTraceExplorer(FakeTraceAgent())
    output = explorer._extract_output({
        "structured_response": {
            "code_logic": "deepagents logic",
            "code_map": [
                {
                    "function_name": "handle_test",
                    "file_path": "src/test.c",
                    "line_start": 1,
                    "line_end": 2,
                    "code_snippet": "int handle_test() {}",
                    "is_entry_point": True,
                    "taint_source": "mg_get_var",
                    "taint_path": "source -> sink",
                }
            ],
        }
    })
    assert isinstance(output, DeepTraceOutput)
    assert output.code_logic == "deepagents logic"
    assert output.code_map[0].function_name == "handle_test"

    messages_only_output = explorer._extract_output({
        "messages": [
            SimpleNamespace(content="analysis before final"),
            SimpleNamespace(content=json.dumps({
                "code_logic": "parsed from ai message",
                "code_map": [
                    {
                        "function_name": "handle_test",
                        "file_path": "src/test.c",
                        "line_start": 1,
                        "line_end": 2,
                        "code_snippet": "int handle_test() {}",
                        "is_entry_point": True,
                        "taint_source": "mg_get_var",
                        "taint_path": "source -> sink",
                    }
                ],
            })),
        ],
    })
    if messages_only_output.code_logic != "parsed from ai message":
        raise AssertionError("trace output should parse structured JSON from AI messages")

    model = explorer._build_model()
    assert getattr(model, "model_name", None) == "fake-model"

    agent = explorer.agent
    assert hasattr(agent, "invoke")

    prompt = explorer._system_prompt() + "\n" + build_exploration_user_message(build_fake_audit_inputs()[0])
    required_guidance = [
        "返回 file:line 后必须使用 read_file",
        "连续 3 次符号未命中",
    ]
    missing = [text for text in required_guidance if text not in prompt]
    if missing:
        raise AssertionError(f"trace prompt missing tool-use guardrails: {missing}")


def verify_deepagents_trace_unstructured_fallback() -> None:
    """A messages-only DeepAgents result should not crash trace exploration."""

    class MessagesOnlyAgent:
        def invoke(self, *_args, **_kwargs):
            return {
                "messages": [
                    SimpleNamespace(content="我已经分析完成，但没有返回 JSON。"),
                ],
            }

    func_info, _ = build_fake_audit_inputs()
    explorer = DeepAgentsTraceExplorer(FakeTraceAgent())
    explorer._agent = MessagesOnlyAgent()

    code_logic, code_map, messages = explorer.run(func_info)

    if "未返回结构化" not in code_logic:
        raise AssertionError("trace fallback should explain missing structured output")
    if len(code_map) != 1 or code_map[0].function_name != func_info.func_name:
        raise AssertionError("trace fallback should preserve entry function context")
    if not messages:
        raise AssertionError("trace fallback should preserve raw messages")


def verify_deepseek_model_options() -> None:
    from utils.chat_model import build_chat_model

    init_settings({
        "api_key": "verification-only",
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-v4-pro",
        "deepseek_thinking": "disabled",
        "deepseek_reasoning_effort": "",
        "project_path": str(PROJECT_ROOT),
        "skills_path": str(PROJECT_ROOT / "skills"),
        "exploit_backend": "filesystem",
    })
    model = build_chat_model()
    if getattr(model, "extra_body", None) != {"thinking": {"type": "disabled"}}:
        raise AssertionError("DeepSeek model should disable thinking mode for tool-calling agents")
    if getattr(model, "reasoning_effort", None):
        raise AssertionError("DeepSeek non-thinking mode should not set reasoning_effort")

    configure_project_root()


def verify_deepagents_audit_runner() -> None:
    from agents.deepagents_audit_runner import DeepAgentsAuditRunner, DeepAuditOutput

    func_info, code_map = build_fake_audit_inputs()
    runner = DeepAgentsAuditRunner(
        agent_name="verification_agent",
        vulnerability_type="command_injection",
        function_info=func_info,
        code_map=code_map,
        system_prompt="verification system",
        user_message="verification user",
        project_path=str(PROJECT_ROOT),
        debug=False,
    )

    backend = runner._build_backend()
    read_result = backend.read("/pyproject.toml", limit=3)
    if read_result.error or 'name = "tsj-audit"' not in read_result.file_data["content"]:
        raise AssertionError("DeepAgents audit runner filesystem is not bound to project root")

    output = runner._extract_output({
        "structured_response": {
            "is_vulnerable": True,
            "confidence": "medium",
            "description": "verified finding",
            "taint_flow": "input -> sink",
            "recommendation": "sanitize input",
            "code_map": [code_map[0].model_dump()],
        }
    })
    assert isinstance(output, DeepAuditOutput)
    result = runner._to_audit_result(output)
    assert result.vulnerability_type == "command_injection"
    assert result.is_vulnerable is True
    assert result.code_map[0].function_name == "handle_test"

    tool_names = {tool.__name__ for tool in runner.tools}
    if tool_names != {"project_go_to_def", "project_find_refs", "project_skill"}:
        raise AssertionError(f"unexpected audit runner tools: {sorted(tool_names)}")

    agent = runner.agent
    assert hasattr(agent, "invoke")
    recursion_limit = runner._invoke_config().get("recursion_limit")
    if recursion_limit < 260:
        raise AssertionError(
            "DeepAgents recursion_limit should be derived from max_tool_calls, "
            f"got {recursion_limit}"
        )


def verify_deepagents_recursion_limit_fallbacks() -> None:
    """GraphRecursionError should not crash the whole audit function."""
    from langgraph.errors import GraphRecursionError

    from agents.deepagents_audit_runner import DeepAgentsAuditRunner
    from agents.deepagents_exploit_runner import DeepAgentsExploitRunner

    class RecursingAgent:
        def invoke(self, *_args, **_kwargs):
            raise GraphRecursionError("verification recursion limit")

    func_info, code_map = build_fake_audit_inputs()

    explorer = DeepAgentsTraceExplorer(FakeTraceAgent())
    explorer._agent = RecursingAgent()
    code_logic, fallback_code_map, messages = explorer.run(func_info)
    if "执行步数上限" not in code_logic:
        raise AssertionError("trace explorer should explain recursion fallback")
    if len(fallback_code_map) != 1 or fallback_code_map[0].function_name != func_info.func_name:
        raise AssertionError("trace explorer fallback should preserve entry function context")
    if not messages:
        raise AssertionError("trace explorer fallback should return diagnostic messages")

    audit_runner = DeepAgentsAuditRunner(
        agent_name="verification_agent",
        vulnerability_type="command_injection",
        function_info=func_info,
        code_map=code_map,
        system_prompt="verification system",
        user_message="verification user",
        project_path=str(PROJECT_ROOT),
        debug=False,
    )
    audit_runner._agent = RecursingAgent()
    audit_result = audit_runner.run()
    if audit_result.is_vulnerable or audit_result.confidence != "low":
        raise AssertionError("audit recursion fallback should return low-confidence non-vulnerable result")
    if "执行步数上限" not in audit_result.description:
        raise AssertionError("audit recursion fallback should explain the limit")

    exploit_runner = DeepAgentsExploitRunner(
        audit_result=AuditResult(
            vulnerability_type="command_injection",
            is_vulnerable=True,
            confidence="medium",
            description="fake vulnerable path",
            code_map=code_map,
        ),
        function_info=func_info,
        code_map=code_map,
        system_prompt="verification exploit system",
        user_message="verification exploit user",
        project_path=str(PROJECT_ROOT),
        debug=False,
    )
    exploit_runner._agent = RecursingAgent()
    exploit_result = exploit_runner.run()
    if exploit_result.success:
        raise AssertionError("exploit recursion fallback should fail closed")
    if not exploit_result.error or "执行步数上限" not in exploit_result.error:
        raise AssertionError("exploit recursion fallback should explain the limit")


def build_fake_audit_inputs() -> tuple[FunctionInfo, List[CodeContext]]:
    func_info = FunctionInfo(
        func_name="handle_test",
        file_path="src/test.c",
        start_line=10,
        end_line=20,
        code_snippet="int handle_test() { return 0; }",
        input="mg_get_var",
        audit_types=["command_injection"],
    )
    code_map = [
        CodeContext(
            function_name=func_info.func_name,
            file_path=func_info.file_path,
            line_start=func_info.start_line,
            line_end=func_info.end_line,
            code_snippet=func_info.code_snippet,
            is_entry_point=True,
            taint_source=func_info.input,
            taint_path="fake source -> fake sink",
        )
    ]
    return func_info, code_map


def verify_specialized_audit_agents_use_deepagents_runner() -> None:
    import agents.command_inject_agent as command_inject_agent
    import agents.path_traversal_agent as path_traversal_agent
    import agents.brute_force_agent as brute_force_agent
    import agents.password_reset_agent as password_reset_agent
    import agents.loop_vulnerability_agent as loop_vulnerability_agent
    import agents.deepagents_audit_runner as deepagents_audit_runner

    func_info, code_map = build_fake_audit_inputs()
    calls: List[Dict] = []

    def fake_run(self):
        calls.append({
            "agent_name": self.agent_name,
            "vulnerability_type": self.vulnerability_type,
            "project_path": self.project_path,
        })
        return AuditResult(
            vulnerability_type=self.vulnerability_type,
            is_vulnerable=False,
            confidence="low",
            description=f"fake {self.vulnerability_type}",
            code_map=self.code_map,
        )

    original_run = deepagents_audit_runner.DeepAgentsAuditRunner.run
    deepagents_audit_runner.DeepAgentsAuditRunner.run = fake_run
    try:
        agents = [
            command_inject_agent.CommandInjectAgent(func_info, code_map, project_path=str(PROJECT_ROOT)),
            path_traversal_agent.PathTraversalAgent(func_info, code_map, project_path=str(PROJECT_ROOT)),
            brute_force_agent.BruteForceAgent(func_info, code_map, project_path=str(PROJECT_ROOT)),
            password_reset_agent.PasswordResetAgent(func_info, code_map, project_path=str(PROJECT_ROOT)),
            loop_vulnerability_agent.LoopVulnerabilityAgent(func_info, code_map, project_path=str(PROJECT_ROOT)),
        ]
        results = [agent.audit() for agent in agents]
    finally:
        deepagents_audit_runner.DeepAgentsAuditRunner.run = original_run

    expected_types = [
        "command_injection",
        "path_traversal",
        "brute_force",
        "password_reset",
        "loop",
    ]
    if [result.vulnerability_type for result in results] != expected_types:
        raise AssertionError("specialized agents did not return expected vulnerability types")
    if [call["vulnerability_type"] for call in calls] != expected_types:
        raise AssertionError("specialized agents did not delegate to DeepAgentsAuditRunner")


def verify_specialized_audit_agents_removed_legacy_runtime() -> None:
    agent_files = [
        PROJECT_ROOT / "agents" / "command_inject_agent.py",
        PROJECT_ROOT / "agents" / "path_traversal_agent.py",
        PROJECT_ROOT / "agents" / "brute_force_agent.py",
        PROJECT_ROOT / "agents" / "password_reset_agent.py",
        PROJECT_ROOT / "agents" / "loop_vulnerability_agent.py",
    ]
    forbidden_tokens = [
        "ToolExecutor",
        "LLMClient",
        "get_config_object",
        "EXPLORATION_TOOLS",
        "ToolRegistry.to_openai_tools",
        "submit_command_inject",
        "submit_path_traversal",
        "submit_brute_force",
        "submit_password_reset",
        "submit_loop_vuln",
    ]
    for file_path in agent_files:
        source = file_path.read_text(encoding="utf-8")
        found = [token for token in forbidden_tokens if token in source]
        if found:
            raise AssertionError(f"{file_path.name} still contains legacy runtime tokens: {found}")


def verify_deepagents_exploit_runner() -> None:
    from agents.deepagents_exploit_runner import DeepExploitOutput, DeepAgentsExploitRunner

    func_info, code_map = build_fake_audit_inputs()
    audit_result = AuditResult(
        vulnerability_type="command_injection",
        is_vulnerable=True,
        confidence="medium",
        description="fake vulnerable path",
        taint_flow="input -> command",
        code_map=code_map,
    )
    runner = DeepAgentsExploitRunner(
        audit_result=audit_result,
        function_info=func_info,
        code_map=code_map,
        system_prompt="verification exploit system",
        user_message="verification exploit user",
        project_path=str(PROJECT_ROOT),
        debug=False,
    )

    backend = runner._build_backend()
    read_result = backend.read("/pyproject.toml", limit=3)
    if read_result.error or 'name = "tsj-audit"' not in read_result.file_data["content"]:
        raise AssertionError("DeepAgents exploit runner filesystem is not bound to project root")

    output = runner._extract_output({
        "structured_response": {
            "success": True,
            "poc_command": "curl http://localhost:8081/",
            "summary": "verified safely",
        }
    })
    assert isinstance(output, DeepExploitOutput)
    result = runner._to_exploit_result(output)
    assert result.vulnerability_type == "command_injection"
    assert result.success is True
    assert result.poc_command.startswith("curl")

    if runner.tools:
        raise AssertionError("Exploit runner should rely on DeepAgents native execute, not custom shell tools")

    prompt = runner._system_prompt()
    if "execute" not in prompt or "OpenSandbox" not in prompt:
        raise AssertionError("Exploit runner prompt should instruct the agent to use OpenSandbox execute")

    agent = runner.agent
    assert hasattr(agent, "invoke")


def verify_exploit_agent_uses_deepagents_runner() -> None:
    import agents.exploit_agent as exploit_agent
    import agents.deepagents_exploit_runner as deepagents_exploit_runner

    func_info, code_map = build_fake_audit_inputs()
    audit_result = AuditResult(
        vulnerability_type="command_injection",
        is_vulnerable=True,
        confidence="medium",
        description="fake vulnerable path",
        code_map=code_map,
    )
    calls: List[Dict] = []

    def fake_run(self):
        calls.append({
            "vulnerability_type": self.audit_result.vulnerability_type,
            "project_path": self.project_path,
        })
        return ExploitResult(
            vulnerability_type=self.audit_result.vulnerability_type,
            success=False,
            poc_command="",
            output="fake exploit",
        )

    original_run = deepagents_exploit_runner.DeepAgentsExploitRunner.run
    deepagents_exploit_runner.DeepAgentsExploitRunner.run = fake_run
    try:
        result = exploit_agent.ExploitAgent(
            audit_result=audit_result,
            function_info=func_info,
            code_map=code_map,
            project_path=str(PROJECT_ROOT),
        ).exploit()
    finally:
        deepagents_exploit_runner.DeepAgentsExploitRunner.run = original_run

    assert result.vulnerability_type == "command_injection"
    assert result.output == "fake exploit"
    if calls != [{"vulnerability_type": "command_injection", "project_path": str(PROJECT_ROOT)}]:
        raise AssertionError("ExploitAgent did not delegate to DeepAgentsExploitRunner")


def verify_exploit_agent_removed_legacy_runtime() -> None:
    source = (PROJECT_ROOT / "agents" / "exploit_agent.py").read_text(encoding="utf-8")
    forbidden_tokens = [
        "LLMClient",
        "get_config_object",
        "EXPLOIT_TOOLS",
        "ToolRegistry.to_openai_tools",
        "submit_exploit",
        "ExploitSubmitTool",
        "project_run_command",
        "project_session_exec",
    ]
    found = [token for token in forbidden_tokens if token in source]
    if found:
        raise AssertionError(f"exploit_agent.py still contains legacy runtime tokens: {found}")

    runner_source = (PROJECT_ROOT / "agents" / "deepagents_exploit_runner.py").read_text(encoding="utf-8")
    runner_forbidden = [
        "ToolExecutor",
        "project_run_command",
        "project_create_session",
        "project_session_exec",
        "project_close_session",
        "project_list_sessions",
    ]
    runner_found = [token for token in runner_forbidden if token in runner_source]
    if runner_found:
        raise AssertionError(f"deepagents_exploit_runner.py still contains legacy shell tokens: {runner_found}")


def verify_opensandbox_upload_filtering() -> None:
    from agents.deepagents_exploit_runner import DeepAgentsExploitRunner
    from config import get_config

    func_info, code_map = build_fake_audit_inputs()
    audit_result = AuditResult(
        vulnerability_type="command_injection",
        is_vulnerable=True,
        confidence="medium",
        description="fake vulnerable path",
        code_map=code_map,
    )
    runner = DeepAgentsExploitRunner(
        audit_result=audit_result,
        function_info=func_info,
        code_map=code_map,
        system_prompt="verification exploit system",
        user_message="verification exploit user",
        project_path=str(PROJECT_ROOT),
        debug=False,
    )
    config = get_config()
    upload_paths = {
        rel_path.as_posix()
        for _, rel_path in runner._iter_project_upload_files(PROJECT_ROOT, config)
    }
    if "pyproject.toml" not in upload_paths:
        raise AssertionError("OpenSandbox upload filtering skipped project files")
    forbidden_prefixes = (".git/", ".venv/", "output/", "audit_output/")
    if any(path.startswith(forbidden_prefixes) for path in upload_paths):
        raise AssertionError("OpenSandbox upload filtering includes excluded directories")

    class FakeSandboxBackend:
        def __init__(self):
            self.commands: list[str] = []
            self.uploaded_paths: list[str] = []

        def execute(self, command: str):
            self.commands.append(command)
            return SimpleNamespace(exit_code=0, output="")

        def upload_files(self, files):
            self.uploaded_paths.extend(path for path, _ in files)
            return [SimpleNamespace(path=path, error=None) for path, _ in files]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_project = Path(tmp_dir)
        (tmp_project / "src").mkdir()
        (tmp_project / "src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
        (tmp_project / ".git").mkdir()
        (tmp_project / ".git" / "config").write_text("[core]\n", encoding="utf-8")

        fake_backend = FakeSandboxBackend()
        runner._upload_project(fake_backend, tmp_project, config)

    if not fake_backend.commands or not fake_backend.commands[0].startswith("mkdir -p /workspace/project"):
        raise AssertionError("OpenSandbox upload did not create the project directory")
    if "/workspace/project/src/main.c" not in fake_backend.uploaded_paths:
        raise AssertionError("OpenSandbox upload did not upload source files")
    if any("/.git/" in path for path in fake_backend.uploaded_paths):
        raise AssertionError("OpenSandbox upload included excluded .git files")


def verify_old_shell_tool_removed() -> None:
    shell_tool_path = PROJECT_ROOT / "tools" / "shell_tool.py"
    if shell_tool_path.exists():
        raise AssertionError("old shell execution tool still exists: tools/shell_tool.py")

    source = (PROJECT_ROOT / "tools" / "__init__.py").read_text(encoding="utf-8")
    if "ShellTool" in source or "shell_tool" in source:
        raise AssertionError("tools.__init__ still imports the old shell execution tool")

    commands = set(ToolRegistry.get_all_commands())
    removed_shell_commands = {
        "run_command",
        "create_session",
        "session_exec",
        "close_session",
        "list_sessions",
    }
    leftovers = commands & removed_shell_commands
    if leftovers:
        raise AssertionError(f"old shell commands are still registered: {sorted(leftovers)}")


def verify_langgraph_studio_entrypoint() -> None:
    config_path = PROJECT_ROOT / "langgraph.json"
    if not config_path.exists():
        raise AssertionError("missing langgraph.json for LangGraph Studio")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("dependencies") != ["."]:
        raise AssertionError("langgraph.json should install the current project as dependency")
    if config.get("graphs", {}).get("trace_audit") != "./agents/studio_graph.py:graph":
        raise AssertionError("langgraph.json does not expose trace_audit graph")
    if config.get("env") != ".env":
        raise AssertionError("langgraph.json should load .env")

    import agents.studio_graph as studio_graph

    if not hasattr(studio_graph.graph, "invoke"):
        raise AssertionError("LangGraph Studio entrypoint did not export an invokable graph")
    if getattr(studio_graph.graph, "checkpointer", None) is not None:
        raise AssertionError("LangGraph Studio graph must not define a custom checkpointer")

    cli_graph = TraceWorkflow(FakeTraceAgent()).graph
    if type(getattr(cli_graph, "checkpointer", None)).__name__ != "InMemorySaver":
        raise AssertionError("TraceWorkflow CLI graph should keep its in-memory checkpointer")


def main() -> None:
    configure_project_root()
    verify_legacy_tool_registry()
    verify_deepagents_filesystem_backend()
    verify_logged_backend_summaries()
    verify_logged_backend_duplicate_and_budget_guards()
    verify_project_tools_share_tool_call_guards()
    verify_tool_logs_include_audit_function_name()
    verify_workflow()
    verify_deepagents_adapter()
    verify_deepagents_trace_unstructured_fallback()
    verify_deepseek_model_options()
    verify_deepagents_audit_runner()
    verify_deepagents_recursion_limit_fallbacks()
    verify_specialized_audit_agents_use_deepagents_runner()
    verify_specialized_audit_agents_removed_legacy_runtime()
    verify_deepagents_exploit_runner()
    verify_exploit_agent_uses_deepagents_runner()
    verify_exploit_agent_removed_legacy_runtime()
    verify_opensandbox_upload_filtering()
    verify_old_shell_tool_removed()
    verify_langgraph_studio_entrypoint()
    print("LangGraph migration verification passed")


if __name__ == "__main__":
    main()
