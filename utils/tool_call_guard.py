#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared guardrails for tool-call loops."""

from __future__ import annotations

import fnmatch
from collections import Counter
from typing import Any


class ToolCallGuard:
    """Enforce per-runner tool-call budgets and duplicate-call limits."""

    def __init__(
        self,
        *,
        max_tool_calls: int | None = None,
        max_repeated_calls: int | None = None,
        blocked_grep_patterns: set[str] | None = None,
    ):
        self.max_tool_calls = max_tool_calls
        self.max_repeated_calls = max_repeated_calls
        self.blocked_grep_patterns = {
            pattern.lower()
            for pattern in (blocked_grep_patterns or set())
        }
        self._tool_call_count = 0
        self._call_counts: Counter[tuple[str, str]] = Counter()

    def check(self, name: str, args: dict[str, Any]) -> str | None:
        if self.max_tool_calls is not None and self._tool_call_count >= self.max_tool_calls:
            return f"已达到工具调用上限 {self.max_tool_calls}，请基于已有上下文直接给出结论"

        self._tool_call_count += 1

        if name == "grep":
            pattern = str(args.get("pattern") or "").strip().lower()
            if any(fnmatch.fnmatch(pattern, blocked) for blocked in self.blocked_grep_patterns):
                return f"禁止搜索危险函数 '{args.get('pattern')}'，请回到入口函数相关数据流分析"

        if self.max_repeated_calls is not None:
            key = (name, repr(sorted(args.items())))
            self._call_counts[key] += 1
            if self._call_counts[key] > self.max_repeated_calls:
                return f"重复工具调用已超过上限 {self.max_repeated_calls}，请停止重复查询并基于已有结果分析"

        return None
