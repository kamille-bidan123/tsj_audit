#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify persisted artifacts use project-relative file_path values."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.trace_agent import TraceAgent
import config as config_module
from config import Config
from models import AuditResult, CodeContext, EntrySpec, FunctionInfo, TraceResult
from utils.path_utils import normalize_entry_specs_file_paths
from utils.export_utils import (
    EXPORT_FORMAT_SARIF,
    EXPORT_FORMAT_SARIF_ISSUES,
    export_results,
    export_to_html,
    export_to_json,
    export_to_markdown,
    merge_checkpoints_and_export,
)


def build_result(project: Path) -> TraceResult:
    helper = CodeContext(
        function_name="run_auth_check",
        file_path=str(project / "src" / "helper.c"),
        line_start=50,
        line_end=68,
        code_snippet="system(user);",
        taint_source="mg_get_var",
        taint_path="handle_login -> run_auth_check",
    )
    return TraceResult(
        function_info=FunctionInfo(
            func_name="handle_login",
            file_path=str(project / "src" / "auth.c"),
            start_line=12,
            end_line=42,
            code_snippet="int handle_login() { return 0; }",
            skill="civetweb_audit",
        ),
        code_logic="ok",
        code_map=[helper],
        audit_results=[
            AuditResult(
                vulnerability_type="command_injection",
                is_vulnerable=True,
                confidence="high",
                description="command reaches shell",
                code_map=[helper],
            )
        ],
        exploit_results=[],
    )


def artifact_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def assert_relative_only(value, project: Path) -> None:
    text = artifact_text(value)
    if str(project) in text:
        raise AssertionError(f"artifact leaked absolute project path: {project}")
    for expected in ("src/auth.c", "src/helper.c"):
        if expected not in text:
            raise AssertionError(f"artifact missing relative path {expected}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project = root / "project"
        output = root / "output"
        (project / "src").mkdir(parents=True)
        output.mkdir()
        result = build_result(project)
        config_module.set_config(Config(project_path=str(project), output_dir=str(output)))
        entries = normalize_entry_specs_file_paths(
            [EntrySpec(func_name="handle_login", file_path=str(project / "src" / "auth.c"))],
            None,
        )
        if entries[0].file_path != "src/auth.c":
            raise AssertionError(f"EntrySpec save path should be project-relative, got {entries[0].file_path}")

        agent = TraceAgent(project_path=str(project), output_dir=str(output))
        agent._save_checkpoint(str(output), result)
        checkpoint = json.loads((output / "checkpoints" / "handle_login.json").read_text(encoding="utf-8"))
        assert_relative_only(checkpoint, project)

        agent._save_conversation_history("trace_agent", result.function_info, [{"role": "assistant", "content": "ok"}])
        conversation = json.loads(
            (output / "conversations" / "trace_agent" / "handle_login.json").read_text(encoding="utf-8")
        )
        if str(project) in artifact_text(conversation):
            raise AssertionError("conversation artifact leaked absolute project path")
        if "src/auth.c" not in artifact_text(conversation):
            raise AssertionError("conversation artifact missing relative function path")

        json_path = output / "result.json"
        export_to_json([result], str(json_path))
        assert_relative_only(json.loads(json_path.read_text(encoding="utf-8")), project)

        html_path = output / "result.html"
        export_to_html([result], str(html_path))
        assert_relative_only(html_path.read_text(encoding="utf-8"), project)

        markdown_dir = output / "result_markdown"
        export_to_markdown([result], str(markdown_dir))
        markdown_text = "\n".join(path.read_text(encoding="utf-8") for path in markdown_dir.rglob("*.md"))
        assert_relative_only(markdown_text, project)

        sarif_path = output / "result.sarif"
        export_results([result], str(sarif_path), EXPORT_FORMAT_SARIF)
        assert_relative_only(json.loads(sarif_path.read_text(encoding="utf-8")), project)

        issues_path = output / "result_issues.sarif"
        export_results([result], str(issues_path), EXPORT_FORMAT_SARIF_ISSUES)
        assert_relative_only(json.loads(issues_path.read_text(encoding="utf-8")), project)

        legacy_output = root / "legacy_output"
        legacy_checkpoints = legacy_output / "checkpoints"
        legacy_checkpoints.mkdir(parents=True)
        (legacy_output / "audit_config.json").write_text(
            json.dumps({"project_path": str(project)}, ensure_ascii=False),
            encoding="utf-8",
        )
        checkpoint_data = result.model_dump()
        checkpoint_data["_checkpoint_meta"] = {
            "func_name": result.function_info.func_name,
            "file_path": result.function_info.file_path,
        }
        (legacy_checkpoints / "handle_login.json").write_text(
            json.dumps(checkpoint_data, ensure_ascii=False),
            encoding="utf-8",
        )
        merge_checkpoints_and_export(str(legacy_output))
        merged_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in legacy_output.iterdir()
            if path.is_file() and path.name.startswith("trace_results_") and path.suffix in {".json", ".html", ".sarif"}
        )
        assert_relative_only(merged_text, project)

    print("relative file_path verification passed")


if __name__ == "__main__":
    main()
