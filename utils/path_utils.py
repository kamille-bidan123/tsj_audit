#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for storing project-relative source file paths."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from models import CodeContext, EntrySpec, FunctionInfo, TraceResult


def project_relative_path(file_path: str, project_path: str | None) -> str:
    """Return file_path relative to project_path when it points inside the project."""
    project_path = project_path or _default_project_path()
    if not file_path or not project_path:
        return file_path

    path = Path(file_path)
    if not path.is_absolute():
        return path.as_posix()

    try:
        return path.resolve().relative_to(Path(project_path).expanduser().resolve()).as_posix()
    except ValueError:
        return path.as_posix()
    except OSError:
        return file_path


def normalize_entry_specs_file_paths(entries: Iterable[EntrySpec], project_path: str | None) -> list[EntrySpec]:
    return [
        entry.model_copy(update={"file_path": project_relative_path(entry.file_path, project_path)})
        for entry in entries
    ]


def normalize_function_info_file_path(func_info: FunctionInfo, project_path: str | None) -> FunctionInfo:
    return func_info.model_copy(update={"file_path": project_relative_path(func_info.file_path, project_path)})


def normalize_code_context_file_path(ctx: CodeContext, project_path: str | None) -> CodeContext:
    return ctx.model_copy(update={"file_path": project_relative_path(ctx.file_path, project_path)})


def normalize_trace_result_file_paths(result: TraceResult, project_path: str | None) -> TraceResult:
    code_map = [normalize_code_context_file_path(ctx, project_path) for ctx in result.code_map]
    audit_results = [
        audit.model_copy(
            update={
                "code_map": [
                    normalize_code_context_file_path(ctx, project_path)
                    for ctx in audit.code_map
                ]
            }
        )
        for audit in result.audit_results
    ]
    return result.model_copy(
        update={
            "function_info": normalize_function_info_file_path(result.function_info, project_path),
            "code_map": code_map,
            "audit_results": audit_results,
        }
    )


def normalize_trace_results_file_paths(results: Iterable[TraceResult], project_path: str | None) -> list[TraceResult]:
    return [normalize_trace_result_file_paths(result, project_path) for result in results]


def _default_project_path() -> str | None:
    try:
        from config import get_config

        project_path = getattr(get_config(), "project_path", None)
    except Exception:
        return None
    return project_path if isinstance(project_path, str) and project_path else None
