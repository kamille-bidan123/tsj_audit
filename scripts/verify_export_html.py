#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the static HTML audit report presentation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import AuditResult, CodeContext, ExploitResult, FunctionInfo, TraceResult
from utils.export_utils import generate_html


def build_sample_results() -> list[TraceResult]:
    entry = FunctionInfo(
        func_name="handle_login",
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
    return [
        TraceResult(
            function_info=entry,
            code_logic='### 登录处理\n- 读取 `user` 参数\n- 执行 **权限检查**\n<script>alert("x")</script>',
            code_map=[context],
            audit_results=[
                AuditResult(
                    vulnerability_type="command_injection",
                    is_vulnerable=True,
                    confidence="high",
                    description='用户输入进入命令执行 <script>alert("x")</script>',
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
        )
    ]


def main() -> None:
    html = generate_html(build_sample_results())
    required_markers = [
        'class="report-shell"',
        'id="reportSearch"',
        'class="summary-grid"',
        'data-search="',
        'data-risk="critical"',
        'data-vuln-types="command_injection"',
        "type-filter-group",
        'data-type-filter="command_injection"',
        "setTypeFilter(this)",
        "Code Map Timeline",
        "失败降级 / 验证状态",
        '<div class="logic markdown-body">',
        "<h3>登录处理</h3>",
        "<li>读取 <code>user</code> 参数</li>",
        "<strong>权限检查</strong>",
    ]
    for marker in required_markers:
        if marker not in html:
            raise AssertionError(f"missing enhanced report marker: {marker}")

    if '<script>alert("x")</script>' in html:
        raise AssertionError("dynamic report fields must be HTML escaped")
    if "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" not in html:
        raise AssertionError("escaped malicious text should remain visible")
    if "LEGACY_INPUT_FIELD_SHOULD_NOT_RENDER" in html:
        raise AssertionError("HTML report should not render FunctionInfo.input")
    if 'data-type-filter="path_traversal"' in html:
        raise AssertionError("HTML report should only expose vulnerable vulnerability types as filters")

    print("export html verification passed")


if __name__ == "__main__":
    main()
