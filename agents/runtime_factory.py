#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Factory functions for selecting the inner agent runtime."""

from __future__ import annotations

from typing import Any


SUPPORTED_AGENT_RUNTIMES = {"opencode", "codex", "claudecode"}


def get_agent_runtime() -> str:
    from config import get_config

    runtime = (get_config().agent_runtime or "codex").strip().lower()
    if runtime not in SUPPORTED_AGENT_RUNTIMES:
        raise ValueError(
            f"unsupported agent_runtime: {runtime}. "
            f"Supported values: {', '.join(sorted(SUPPORTED_AGENT_RUNTIMES))}"
        )
    return runtime


def create_trace_explorer(trace_agent: Any):
    runtime = get_agent_runtime()
    from agents.agent_runtime_runner import AgentRuntimeTraceExplorer

    return AgentRuntimeTraceExplorer(trace_agent, runtime=runtime)


def create_entry_discovery_runner(**kwargs):
    runtime = get_agent_runtime()
    from agents.agent_runtime_runner import AgentRuntimeEntryDiscoveryRunner

    return AgentRuntimeEntryDiscoveryRunner(runtime=runtime, **kwargs)


def create_audit_runner(**kwargs):
    runtime = get_agent_runtime()
    from agents.agent_runtime_runner import AgentRuntimeAuditRunner

    return AgentRuntimeAuditRunner(runtime=runtime, **kwargs)


def create_exploit_runner(**kwargs):
    runtime = get_agent_runtime()
    from agents.agent_runtime_runner import AgentRuntimeExploitRunner

    return AgentRuntimeExploitRunner(runtime=runtime, **kwargs)
