#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify Markdown audit report export."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import AuditResult, CodeContext, ExploitResult, FunctionInfo, TraceResult
from utils.export_utils import EXPORT_FORMAT_MARKDOWN, export_results


def build_sample_results() -> list[TraceResult]:
    entry = FunctionInfo(
        func_name="handle/login?<main>",
        file_path="src/auth.c",
        start_line=12,
        end_line=42,
        code_snippet='int handle_login() { return strcmp(user, "<admin>"); }',
        skill="civetweb_audit",
    )
    context = CodeContext(
        function_name="run_auth_check",
        file_path="src/auth.c",
        line_start=50,
        line_end=68,
        code_snippet='system("<unsafe>");',
        is_entry_point=False,
        taint_source="mg_get_var",
        taint_path="handle_login -> run_auth_check",
    )
    clean_entry = FunctionInfo(
        func_name="handle_status",
        file_path="src/status.c",
        start_line=80,
        end_line=96,
        code_snippet='int handle_status() { return 0; }',
        skill="civetweb_audit",
    )
    return [
        TraceResult(
            function_info=entry,
            code_logic="### 登录处理\n- 读取 user 参数\n- 执行权限检查",
            code_map=[context],
            audit_results=[
                AuditResult(
                    vulnerability_type="command_injection",
                    finding_id="command_injection_001",
                    title="user reaches shell",
                    severity="high",
                    is_vulnerable=True,
                    confidence="high",
                    description="用户输入进入命令执行",
                    taint_flow="mg_get_var -> system",
                    recommendation="使用参数化 API，避免 shell 拼接",
                    code_map=[context],
                ),
                AuditResult(
                    vulnerability_type="path_traversal",
                    is_vulnerable=False,
                    confidence="low",
                    description="未发现路径穿越",
                    code_map=[],
                ),
            ],
            exploit_results=[
                ExploitResult(
                    vulnerability_type="command_injection",
                    success=True,
                    poc_command="curl http://target/login",
                    output="pwned",
                )
            ],
        ),
        TraceResult(
            function_info=clean_entry,
            code_logic="读取状态并返回固定响应",
            code_map=[],
            audit_results=[
                AuditResult(
                    vulnerability_type="command_injection",
                    is_vulnerable=False,
                    confidence="low",
                    description="未发现命令注入",
                    code_map=[],
                )
            ],
            exploit_results=[],
        ),
    ]


def main() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="tsj-markdown-export-"))
    try:
        report_dir = tmpdir / "trace_results_markdown"
        returned_path = export_results(build_sample_results(), str(report_dir), EXPORT_FORMAT_MARKDOWN)
        if Path(returned_path) != report_dir:
            raise AssertionError("markdown export should return the report directory path")

        all_dir = report_dir / "all"
        vulnerable_dir = report_dir / "vulnerable"
        for expected_dir in [all_dir, vulnerable_dir]:
            if not expected_dir.is_dir():
                raise AssertionError(f"markdown export should create directory: {expected_dir.name}")
            if not (expected_dir / "README.md").exists():
                raise AssertionError(f"markdown export should create {expected_dir.name}/README.md index")

        all_markdown_files = sorted(path.name for path in all_dir.glob("*.md"))
        if all_markdown_files != ["001_handle_login_main.md", "002_handle_status.md", "README.md"]:
            raise AssertionError(f"unexpected all markdown files: {all_markdown_files}")

        vulnerable_markdown_files = sorted(path.name for path in vulnerable_dir.glob("*.md"))
        if vulnerable_markdown_files != ["001_handle_login_main.md", "README.md"]:
            raise AssertionError(f"unexpected vulnerable markdown files: {vulnerable_markdown_files}")

        index = (all_dir / "README.md").read_text(encoding="utf-8")
        vulnerable_index = (vulnerable_dir / "README.md").read_text(encoding="utf-8")
        report = (all_dir / "001_handle_login_main.md").read_text(encoding="utf-8")

        required_index_markers = [
            "# 代码安全审计 Markdown 报告",
            "| # | 函数 | 风险 | 漏洞类型 | 报告 |",
            "[handle/login?&lt;main&gt;](001_handle_login_main.md)",
            "command_injection",
        ]
        for marker in required_index_markers:
            if marker not in index:
                raise AssertionError(f"missing markdown index marker: {marker}")
        if "handle_status" not in index:
            raise AssertionError("all markdown index should include clean functions")
        if "handle_status" in vulnerable_index:
            raise AssertionError("vulnerable markdown index should exclude clean functions")

        required_report_markers = [
            "# handle/login?<main>",
            "## 函数概览",
            "- 文件：`src/auth.c`",
            "- 行号：`12-42`",
            "## 入口代码",
            '```c\nint handle_login() { return strcmp(user, "<admin>"); }\n```',
            "## 业务逻辑",
            "### 登录处理",
            "## Code Map",
            "### 1. run_auth_check",
            '```c\nsystem("<unsafe>");\n```',
            "## 漏洞审计结果",
            "### 1. command_injection",
            "- 状态：存在漏洞",
            "- Finding ID：`command_injection_001`",
            "#### 相关代码上下文",
            "## 漏洞利用结果",
            "### 1. command_injection",
            "- 状态：利用成功",
            "curl http://target/login",
            "pwned",
        ]
        for marker in required_report_markers:
            if marker not in report:
                raise AssertionError(f"missing markdown report marker: {marker}")

        print("export markdown verification passed")
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
