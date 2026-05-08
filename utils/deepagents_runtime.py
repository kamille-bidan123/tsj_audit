#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared runtime helpers for DeepAgents runners."""

from __future__ import annotations

from typing import Any

try:
    from langgraph.errors import GraphRecursionError
except Exception:  # pragma: no cover - only used when dependencies are missing.
    class GraphRecursionError(RuntimeError):
        """Fallback type for environments without LangGraph installed."""


def build_deepagents_invoke_config(config: Any | None = None) -> dict[str, int]:
    """Build LangGraph invoke config for DeepAgents runners.

    LangGraph counts internal super-steps, not user-visible LLM turns. A single
    tool-heavy DeepAgents turn can consume multiple super-steps, so the graph
    limit must be large enough for the explicit tool-call budget to take effect.
    """
    if config is None:
        from config import get_config

        config = get_config()
    return {"recursion_limit": calculate_deepagents_recursion_limit(config)}


def calculate_deepagents_recursion_limit(config: Any) -> int:
    max_turns = _coerce_int(getattr(config, "max_turns", 50), default=50, minimum=1)
    max_tool_calls = _coerce_int(
        getattr(config, "max_tool_calls", 0),
        default=0,
        minimum=0,
    )
    return max(
        25,
        max_turns * 3,
        max_tool_calls * 2 + 20,
    )


def recursion_limit_message(stage: str, config: Any | None = None) -> str:
    invoke_config = build_deepagents_invoke_config(config)
    return (
        f"{stage} 达到 LangGraph 执行步数上限 "
        f"{invoke_config['recursion_limit']}，已停止 DeepAgents 工具循环。"
    )


def _coerce_int(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)
