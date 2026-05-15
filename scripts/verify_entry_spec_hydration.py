#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify lightweight EntrySpec JSON stays lightweight until Trace runtime."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import ValidationError

from agents.trace_agent import TraceAgent
from models import EntrySpec


def verify_lightweight_entry_spec_json_is_loaded_without_hydration() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        source = project / "src" / "web.cpp"
        source.parent.mkdir()
        source.write_text(
            """class UrlApiHandler {
public:
    bool handlePost(CivetServer* server, struct mg_connection* conn)
    {
        auto data = server->getPostData(conn);
        return true;
    }
};
""",
            encoding="utf-8",
        )
        entries_path = project / "entries.json"
        entries_path.write_text(
            json.dumps(
                [
                    {
                        "func_name": "UrlApiHandler::handlePost",
                        "file_path": "src/web.cpp",
                        "start_line": 3,
                        "skill": "civetweb_audit",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        results = TraceAgent(project_path=str(project)).load_entry_results(str(entries_path))

        if len(results) != 1:
            raise AssertionError(f"expected one hydrated entry, got {len(results)}")
        entry = results[0]
        if not isinstance(entry, EntrySpec):
            raise AssertionError("lightweight entry should remain EntrySpec before Trace runtime")
        if entry.func_name != "UrlApiHandler::handlePost":
            raise AssertionError(f"unexpected func_name: {entry.func_name}")
        if entry.start_line != 3:
            raise AssertionError(f"unexpected start_line: {entry.start_line}")
        if "input" in entry.model_dump():
            raise AssertionError("EntrySpec should not expose legacy input field")


def verify_entry_spec_rejects_input_field() -> None:
    try:
        EntrySpec(
            func_name="handle",
            file_path="web.c",
            skill="civetweb_audit",
            input="legacy field should be rejected",
        )
    except ValidationError:
        return
    raise AssertionError("EntrySpec should reject legacy input field")


def verify_scan_json_rejects_function_info_shape() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        entries_path = project / "old_function_info.json"
        entries_path.write_text(
            json.dumps(
                [
                    {
                        "func_name": "handle",
                        "file_path": "web.c",
                        "start_line": 1,
                        "end_line": 3,
                        "code_snippet": "1: int handle() { return 0; }",
                        "skill": "civetweb_audit",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        try:
            TraceAgent(project_path=str(project)).load_entry_results(str(entries_path))
        except ValueError as exc:
            if "EntrySpec" not in str(exc):
                raise AssertionError(f"unexpected rejection error: {exc}")
            return
        raise AssertionError("--entry JSON should reject old FunctionInfo[] shape")


def verify_scan_rejects_json_input() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        entries_path = project / "entries.json"
        entries_path.write_text("[]", encoding="utf-8")
        try:
            TraceAgent(project_path=str(project)).load_scan_results(str(entries_path))
        except ValueError as exc:
            if "--entry" not in str(exc):
                raise AssertionError(f"unexpected scan rejection error: {exc}")
            return
        raise AssertionError("--scan should reject JSON input")


if __name__ == "__main__":
    verify_lightweight_entry_spec_json_is_loaded_without_hydration()
    verify_entry_spec_rejects_input_field()
    verify_scan_json_rejects_function_info_shape()
    verify_scan_rejects_json_input()
    print("entry spec loading verification passed")
