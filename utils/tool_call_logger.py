#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thread-safe tool call logging with shared call ids."""

from __future__ import annotations

import itertools
import threading
from typing import Any


class ToolCallLogger:
    """Emit paired start/end logs for concurrent tool calls."""

    _counter = itertools.count(1)
    _lock = threading.Lock()
    _max_preview_chars = 1200

    @classmethod
    def start(
        cls,
        tool_name: str,
        arguments: Any,
        *,
        audit_function_name: str | None = None,
        debug: bool = False,
    ) -> int:
        call_id = next(cls._counter)
        cls.log(
            call_id,
            "start",
            tool_name,
            f"args: {cls.preview(arguments)}" if debug else "",
            audit_function_name=audit_function_name,
        )
        return call_id

    @classmethod
    def end(
        cls,
        call_id: int,
        tool_name: str,
        result: Any,
        *,
        audit_function_name: str | None = None,
        debug: bool = False,
    ) -> None:
        cls.log(
            call_id,
            "end",
            tool_name,
            f"ret:\n{cls.preview(result)}" if debug else "",
            audit_function_name=audit_function_name,
        )

    @classmethod
    def error(
        cls,
        call_id: int,
        tool_name: str,
        exc: Exception,
        *,
        audit_function_name: str | None = None,
        debug: bool = False,
    ) -> None:
        cls.log(
            call_id,
            "error",
            tool_name,
            f"{type(exc).__name__}: {exc}",
            audit_function_name=audit_function_name,
        )

    @classmethod
    def log(
        cls,
        call_id: int,
        phase: str,
        tool_name: str,
        detail: str,
        *,
        audit_function_name: str | None = None,
    ) -> None:
        thread_name = threading.current_thread().name
        function_prefix = f"[{audit_function_name or 'unknown_function'}] "
        detail_text = f"\n{detail}" if detail else ""
        with cls._lock:
            print(
                f"{function_prefix}[tool#{call_id} {phase}] {tool_name}"
                f"{detail_text}\n"
                f"thread: {thread_name}",
                flush=True,
            )

    @classmethod
    def preview(cls, value: Any) -> str:
        text = str(value)
        if len(text) <= cls._max_preview_chars:
            return text
        return f"{text[:cls._max_preview_chars]}... [truncated {len(text) - cls._max_preview_chars} chars]"
