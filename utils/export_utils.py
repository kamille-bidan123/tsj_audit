#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出工具 - 生成各种格式的审计报告
"""

from typing import List
import json


def generate_html(results: List['TraceResult']) -> str:
    """
    生成 HTML 格式的审计报告

    Args:
        results: TraceResult 列表

    Returns:
        HTML 字符串
    """
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码安全审计报告</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #2c3e50;
            margin-bottom: 30px;
            padding: 20px;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .entry-item {
            background: #fff;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .entry-header {
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background-color 0.2s;
        }
        .entry-header:hover {
            background: #f8f9fa;
        }
        .entry-title {
            font-size: 18px;
            font-weight: 600;
            color: #2c3e50;
        }
        .entry-meta {
            font-size: 14px;
            color: #7f8c8d;
            margin-top: 5px;
        }
        .toggle-icon {
            font-size: 20px;
            color: #95a5a6;
            transition: transform 0.3s;
        }
        .entry-item.expanded .toggle-icon {
            transform: rotate(90deg);
        }
        .entry-content {
            display: none;
            padding: 20px;
            border-top: 1px solid #eee;
            background: #fafbfc;
        }
        .entry-item.expanded .entry-content {
            display: block;
        }
        .section {
            margin-bottom: 20px;
        }
        .section-title {
            font-size: 16px;
            font-weight: 600;
            color: #34495e;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 2px solid #3498db;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .info-item {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
        }
        .info-label {
            font-size: 12px;
            color: #7f8c8d;
            text-transform: uppercase;
        }
        .info-value {
            font-size: 14px;
            color: #2c3e50;
            word-break: break-all;
        }
        .code-block {
            background: #282c34;
            color: #abb2bf;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            margin: 10px 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .tag {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
        }
        .tag-danger {
            background: #fee2e2;
            color: #dc2626;
        }
        .tag-warning {
            background: #fef3c7;
            color: #d97706;
        }
        .tag-success {
            background: #d1fae5;
            color: #059669;
        }
        .tag-info {
            background: #dbeafe;
            color: #2563eb;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #34495e;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .nested-item {
            background: #fafbfc;
            border: 1px solid #e1e4e8;
            border-radius: 4px;
            padding: 15px;
            margin: 10px 0;
        }
        .nested-title {
            font-weight: 600;
            color: #24292e;
            margin-bottom: 10px;
        }
        details {
            margin: 10px 0;
        }
        summary {
            cursor: pointer;
            padding: 10px;
            background: #f6f8fa;
            border-radius: 4px;
            list-style: none;
            font-weight: 500;
        }
        summary:hover {
            background: #eaecef;
        }
        summary::-webkit-details-marker {
            display: none;
        }
        summary::before {
            content: '▶ ';
            display: inline-block;
            transition: transform 0.2s;
        }
        details[open] summary::before {
            transform: rotate(90deg);
        }
        .empty-state {
            text-align: center;
            color: #95a5a6;
            padding: 30px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>代码安全审计报告</h1>
"""

    for idx, result in enumerate(results, 1):
        func_info = result.function_info
        html += f"""
        <div class="entry-item" id="entry-{idx}">
            <div class="entry-header" onclick="toggleEntry(this)">
                <div>
                    <div class="entry-title">#{idx} {func_info.func_name}</div>
                    <div class="entry-meta">
                        {func_info.file_path} |
                        行 {func_info.start_line}-{func_info.end_line} |
                        {func_info.project_type} / {func_info.attack_surface}
                    </div>
                </div>
                <span class="toggle-icon">▶</span>
            </div>
            <div class="entry-content">
"""

        # 函数信息
        html += """
                <div class="section">
                    <div class="section-title">函数信息</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">函数名</div>
                            <div class="info-value">""" + func_info.func_name + """</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">文件路径</div>
                            <div class="info-value">""" + func_info.file_path + """</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">行号范围</div>
                            <div class="info-value">""" + str(func_info.start_line) + """ - """ + str(func_info.end_line) + """</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">项目类型</div>
                            <div class="info-value">""" + func_info.project_type + """</div>
                        </div>
                    </div>
                    <details>
                        <summary>查看代码片段</summary>
                        <div class="code-block">""" + _escape_html(func_info.code_snippet) + """</div>
                    </details>
                </div>
"""

        # Code Map
        html += """
                <div class="section">
                    <div class="section-title">代码映射 (Code Map)</div>
"""
        if result.code_map:
            html += f"""                    <p>共 {len(result.code_map)} 个相关函数</p>
"""
            for i, ctx in enumerate(result.code_map, 1):
                is_entry = "是" if ctx.is_entry_point else "否"
                taint_src = ctx.taint_source or "无"
                taint_path = ctx.taint_path or "无"

                html += f"""
                    <details>
                        <summary>
                            <strong>{ctx.function_name}</strong>
                            <span class="tag tag-info">{ctx.file_path}:{ctx.line_start}-{ctx.line_end}</span>
                        </summary>
                        <div class="nested-item">
                            <div class="info-grid">
                                <div class="info-item">
                                    <div class="info-label">入口函数</div>
                                    <div class="info-value">{is_entry}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">污染源</div>
                                    <div class="info-value">{taint_src}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">污染路径</div>
                                    <div class="info-value">{taint_path}</div>
                                </div>
                            </div>
                            <details>
                                <summary>查看代码</summary>
                                <div class="code-block">""" + _escape_html(ctx.code_snippet) + """</div>
                            </details>
                        </div>
                    </details>
"""
        else:
            html += """
                    <div class="empty-state">暂无代码映射数据</div>
"""
        html += """
                </div>
"""

        # 审计结果
        html += """
                <div class="section">
                    <div class="section-title">漏洞审计结果</div>
"""
        if result.audit_results:
            for i, audit in enumerate(result.audit_results, 1):
                vuln_type = audit.vulnerability_type
                is_vuln = "存在漏洞" if audit.is_vulnerable else "未发现问题"
                tag_class = "tag-danger" if audit.is_vulnerable else "tag-success"
                confidence_map = {"high": "高", "medium": "中", "low": "低"}
                confidence = confidence_map.get(audit.confidence.lower(), audit.confidence)

                confidence_class = "tag-danger" if audit.confidence.lower() == "high" else ("tag-warning" if audit.confidence.lower() == "medium" else "tag-info")

                html += f"""
                    <details>
                        <summary>
                            <span class="tag {tag_class}">{is_vuln}</span>
                            <strong>{vuln_type}</strong>
                            <span class="tag {confidence_class}">置信度：{confidence}</span>
                        </summary>
                        <div class="nested-item">
                            <div class="info-grid">
                                <div class="info-item">
                                    <div class="info-label">漏洞类型</div>
                                    <div class="info-value">{vuln_type}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">是否存漏洞</div>
                                    <div class="info-value">{is_vuln}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">置信度</div>
                                    <div class="info-value">{confidence}</div>
                                </div>
                            </div>
                            <p><strong>描述:</strong></p>
                            <p>{audit.description}</p>
"""
                if audit.taint_flow:
                    html += f"""
                            <p><strong>污点流向:</strong></p>
                            <div class="code-block">{_escape_html(audit.taint_flow)}</div>
"""
                if audit.recommendation:
                    html += f"""
                            <p><strong>修复建议:</strong></p>
                            <div class="code-block">{_escape_html(audit.recommendation)}</div>
"""
                if audit.code_map:
                    html += """
                            <details>
                                <summary>相关代码上下文</summary>
"""
                    for ctx in audit.code_map:
                        html += f"""
                                <div class="nested-item">
                                    <div class="nested-title">{ctx.function_name} @ {ctx.file_path}:{ctx.line_start}-{ctx.line_end}</div>
                                    <div class="code-block">{_escape_html(ctx.code_snippet)}</div>
                                </div>
"""
                    html += """
                            </details>
"""
                html += """
                        </div>
                    </details>
"""
        else:
            html += """
                    <div class="empty-state">暂无漏洞审计结果</div>
"""
        html += """
                </div>
"""

        # 漏洞利用结果
        html += """
                <div class="section">
                    <div class="section-title">漏洞利用结果</div>
"""
        if result.exploit_results:
            for i, exploit in enumerate(result.exploit_results, 1):
                success = "利用成功" if exploit.success else "利用失败"
                tag_class = "tag-danger" if exploit.success else "tag-warning"

                html += f"""
                    <details>
                        <summary>
                            <span class="tag {tag_class}">{success}</span>
                            <strong>{exploit.vulnerability_type}</strong>
                        </summary>
                        <div class="nested-item">
                            <div class="info-grid">
                                <div class="info-item">
                                    <div class="info-label">漏洞类型</div>
                                    <div class="info-value">{exploit.vulnerability_type}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">利用状态</div>
                                    <div class="info-value">{success}</div>
                                </div>
                            </div>
                            <p><strong>PoC 命令:</strong></p>
                            <div class="code-block">{_escape_html(exploit.poc_command)}</div>
"""
                if exploit.output:
                    html += f"""
                            <p><strong>执行输出:</strong></p>
                            <div class="code-block">{_escape_html(exploit.output)}</div>
"""
                if exploit.error:
                    html += f"""
                            <p><strong>错误信息:</strong></p>
                            <div class="code-block">{_escape_html(exploit.error)}</div>
"""
                html += """
                        </div>
                    </details>
"""
        else:
            html += """
                    <div class="empty-state">暂无漏洞利用结果</div>
"""
        html += """
                </div>
"""

        html += """
            </div>
        </div>
"""

    html += """
    </div>
    <script>
        function toggleEntry(header) {
            const entry = header.parentElement;
            entry.classList.toggle('expanded');
        }
    </script>
</body>
</html>
"""

    return html


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;"))


def export_to_html(results: List['TraceResult'], output_path: str) -> str:
    """
    导出审计结果为 HTML 文件

    Args:
        results: TraceResult 列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    html_content = generate_html(results)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


def export_to_json(results: List['TraceResult'], output_path: str) -> str:
    """
    导出审计结果为 JSON 文件

    Args:
        results: TraceResult 列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    from models import TraceResult
    data = [r.model_dump() for r in results]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_path


def export_results(
    results: List['TraceResult'],
    output_path: str,
    format: str = "json"
) -> str:
    """
    导出审计结果

    Args:
        results: TraceResult 列表
        output_path: 输出路径
        format: 输出格式 ("json" 或 "html")

    Returns:
        输出文件路径
    """
    if format == "json":
        return export_to_json(results, output_path)
    elif format == "html":
        return export_to_html(results, output_path)
    else:
        raise ValueError(f"不支持的格式：{format}")
