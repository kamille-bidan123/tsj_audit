#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Logging proxy for DeepAgents filesystem/sandbox backends."""

from __future__ import annotations

from typing import Any

from utils.tool_call_guard import ToolCallGuard
from utils.tool_call_logger import ToolCallLogger


class LoggedBackend:
    """Delegate backend operations while logging native DeepAgents tool calls."""

    def __init__(
        self,
        backend: Any,
        *,
        prefix: str = "",
        audit_function_name: str | None = None,
        max_tool_calls: int | None = None,
        max_repeated_calls: int | None = None,
        blocked_grep_patterns: set[str] | None = None,
        tool_guard: ToolCallGuard | None = None,
    ):
        self._backend = backend
        self._prefix = prefix
        self.audit_function_name = audit_function_name
        self.debug = self._is_debug_enabled()
        self._tool_guard = tool_guard or ToolCallGuard(
            max_tool_calls=max_tool_calls,
            max_repeated_calls=max_repeated_calls,
            blocked_grep_patterns=blocked_grep_patterns,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    @property
    def id(self) -> str:
        return getattr(self._backend, "id", type(self._backend).__name__)

    def ls(self, path: str):
        return self._call("ls", {"path": path}, self._backend.ls, path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return self._call(
            "read_file",
            {"file_path": file_path, "offset": offset, "limit": limit},
            self._backend.read,
            file_path,
            offset=offset,
            limit=limit,
        )

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        return self._call(
            "grep",
            {"pattern": pattern, "path": path, "glob": glob},
            self._backend.grep,
            pattern,
            path=path,
            glob=glob,
        )

    def glob(self, pattern: str, path: str = "/"):
        return self._call(
            "glob",
            {"pattern": pattern, "path": path},
            self._backend.glob,
            pattern,
            path=path,
        )

    def write(self, file_path: str, content: str):
        return self._call(
            "write_file",
            {"file_path": file_path, "content": f"<{len(content)} chars>"},
            self._backend.write,
            file_path,
            content,
        )

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ):
        return self._call(
            "edit_file",
            {
                "file_path": file_path,
                "old_string": f"<{len(old_string)} chars>",
                "new_string": f"<{len(new_string)} chars>",
                "replace_all": replace_all,
            },
            self._backend.edit,
            file_path,
            old_string,
            new_string,
            replace_all=replace_all,
        )

    def execute(self, command: str, *, timeout: int | None = None):
        return self._call(
            "execute",
            {"command": command, "timeout": timeout},
            self._backend.execute,
            command,
            timeout=timeout,
        )

    def upload_files(self, files: list[tuple[str, bytes]]):
        args = {
            "files": [
                {"path": path, "bytes": len(content)}
                for path, content in files[:5]
            ],
            "count": len(files),
        }
        return self._call("upload_files", args, self._backend.upload_files, files)

    def download_files(self, paths: list[str]):
        return self._call(
            "download_files",
            {"paths": paths[:5], "count": len(paths)},
            self._backend.download_files,
            paths,
        )

    def _call(self, name: str, args: dict[str, Any], func, *func_args, **func_kwargs):
        tool_name = f"{self._prefix}.{name}" if self._prefix else name
        call_id = ToolCallLogger.start(
            tool_name,
            args,
            audit_function_name=self.audit_function_name,
            debug=self.debug,
        )
        guard_error = self._guard_call(name, args)
        if guard_error is not None:
            result = _ErrorResult(error=guard_error)
            ToolCallLogger.end(
                call_id,
                tool_name,
                self._summarize_result(result),
                audit_function_name=self.audit_function_name,
                debug=self.debug,
            )
            return result

        try:
            result = func(*func_args, **func_kwargs)
        except Exception as exc:
            ToolCallLogger.error(
                call_id,
                tool_name,
                exc,
                audit_function_name=self.audit_function_name,
                debug=self.debug,
            )
            raise
        ToolCallLogger.end(
            call_id,
            tool_name,
            self._summarize_result(result),
            audit_function_name=self.audit_function_name,
            debug=self.debug,
        )
        return result

    @staticmethod
    def _is_debug_enabled() -> bool:
        try:
            from config import get_config

            return bool(get_config().debug)
        except Exception:
            return False

    def _guard_call(self, name: str, args: dict[str, Any]) -> str | None:
        return self._tool_guard.check(name, args)

    def _summarize_result(self, result: Any) -> str:
        error = getattr(result, "error", None)
        if error:
            return f"error: {error}"

        if hasattr(result, "entries"):
            return self._summarize_paths("entries", getattr(result, "entries", []))
        if hasattr(result, "matches"):
            return self._summarize_paths("matches", getattr(result, "matches", []))
        if hasattr(result, "file_data"):
            file_data = getattr(result, "file_data", None) or {}
            content = file_data.get("content", "")
            encoding = file_data.get("encoding", "unknown")
            return f"encoding={encoding}, chars={len(content)}, preview={ToolCallLogger.preview(content)}"
        if hasattr(result, "output"):
            output = getattr(result, "output", "")
            exit_code = getattr(result, "exit_code", None)
            return f"exit_code={exit_code}, output={ToolCallLogger.preview(output)}"
        if isinstance(result, list):
            errors = [item for item in result if getattr(item, "error", None)]
            return f"items={len(result)}, errors={len(errors)}"

        return ToolCallLogger.preview(result)

    def _summarize_paths(self, label: str, items: list[Any]) -> str:
        paths = []
        for item in items[:5]:
            if isinstance(item, dict):
                paths.append(item.get("path", str(item)))
            else:
                paths.append(str(item))
        suffix = "" if len(items) <= 5 else f", ... +{len(items) - 5}"
        return f"{label}={len(items)} [{', '.join(paths)}{suffix}]"


class _ErrorResult:
    def __init__(self, *, error: str):
        self.error = error
