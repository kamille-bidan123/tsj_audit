#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出工具 - 生成各种格式的审计报告
"""

from typing import List
import json

# 导出格式常量
EXPORT_FORMAT_JSON = "json"
EXPORT_FORMAT_HTML = "html"
EXPORT_FORMAT_SARIF = "sarif"
EXPORT_FORMAT_SARIF_ISSUES = "sarif-issues"
EXPORT_FORMAT_TEXT = "text"


def merge_checkpoints_and_export(output_dir: str, debug: bool = False) -> List[TraceResult]:
    """
    合并所有 checkpoint 并导出最终报告

    Args:
        output_dir: 输出目录路径
        debug: 是否输出调试信息

    Returns:
        合并后的 TraceResult 列表
    """
    import glob
    import sys
    from pathlib import Path
    import datetime
    from models import TraceResult

    checkpoint_dir = Path(output_dir) / "checkpoints"
    checkpoint_files = sorted(glob.glob(str(checkpoint_dir / "*.json")))

    if debug:
        print(f"\n[合并] 找到 {len(checkpoint_files)} 个检查点文件", file=sys.stderr)

    results = []
    for checkpoint_file in checkpoint_files:
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.pop("_checkpoint_meta", None)
            if meta:
                result = TraceResult.model_validate(data)
                results.append(result)
                if debug:
                    print(f"  [合并] {checkpoint_file}", file=sys.stderr)
        except Exception as e:
            if debug:
                print(f"  [警告] 合并检查点失败 ({checkpoint_file}): {e}", file=sys.stderr)

    # 导出最终结果
    if results:
        # 按函数名排序
        results.sort(key=lambda x: x.function_info.func_name)

        # 时间戳用于文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"trace_results_{timestamp}"

        # 导出 JSON
        json_path = str(Path(output_dir) / f"{output_filename}.json")
        export_results(results, json_path, EXPORT_FORMAT_JSON)
        if debug:
            print(f"[导出] JSON: {json_path}", file=sys.stderr)

        # 导出 HTML
        html_path = str(Path(output_dir) / f"{output_filename}.html")
        export_results(results, html_path, EXPORT_FORMAT_HTML)
        if debug:
            print(f"[导出] HTML: {html_path}", file=sys.stderr)

        searif_path = str(Path(output_dir) / f"{output_filename}.sarif")
        export_results(results, searif_path, EXPORT_FORMAT_SARIF)

        searif_path = str(Path(output_dir) / f"{output_filename}_issues.sarif")
        export_results(results, searif_path, EXPORT_FORMAT_SARIF_ISSUES)

        print(f"\n[完成] 审计完成，共 {len(results)} 个函数")
        print(f"输出文件: {output_filename}.json, {output_filename}.html")
    else:
        print("\n[警告] 没有找到任何审计结果")

    return results


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
            background: #e9ecef;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #1a1a2e;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            color: #fff;
        }
        .entry-item {
            background: #fff;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.12);
            overflow: hidden;
            border: 1px solid #dee2e6;
        }
        .entry-header {
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background-color 0.2s;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-bottom: 2px solid #dee2e6;
        }
        .entry-header:hover {
            background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%);
        }
        .entry-title {
            font-size: 18px;
            font-weight: 700;
            color: #495057;
        }
        .entry-meta {
            font-size: 13px;
            color: #6c757d;
            margin-top: 5px;
        }
        .toggle-icon {
            font-size: 20px;
            color: #6c757d;
            transition: transform 0.3s;
            background: #dee2e6;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .entry-item.expanded .toggle-icon {
            transform: rotate(90deg);
            background: #495057;
            color: #fff;
        }
        .entry-content {
            display: none;
            padding: 20px;
            border-top: 3px solid #667eea;
            background: #f8f9fa;
        }
        .entry-item.expanded .entry-content {
            display: block;
        }
        .section {
            margin-bottom: 20px;
            padding: 15px;
            background: #fff;
            border-radius: 6px;
            border: 1px solid #dee2e6;
        }
        .section-title {
            font-size: 16px;
            font-weight: 700;
            color: #495057;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 3px solid #667eea;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .info-item {
            background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
            padding: 12px;
            border-radius: 6px;
            border: 1px solid #90caf9;
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
            background: linear-gradient(135deg, #fff9e6 0%, #fff3cd 100%);
            border: 1px solid #ffc107;
            border-radius: 6px;
            padding: 15px;
            margin: 10px 0;
        }
        .nested-title {
            font-weight: 700;
            color: #856404;
            margin-bottom: 10px;
        }
        details {
            margin: 10px 0;
        }
        summary {
            cursor: pointer;
            padding: 12px 15px;
            background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%);
            border-radius: 6px;
            list-style: none;
            font-weight: 600;
            color: #495057;
            border: 1px solid #ced4da;
        }
        summary:hover {
            background: linear-gradient(135deg, #dee2e6 0%, #ced4da 100%);
        }
        summary::-webkit-details-marker {
            display: none;
        }
        summary::before {
            content: '▶ ';
            display: inline-block;
            transition: transform 0.2s;
            color: #667eea;
        }
        details[open] summary::before {
            transform: rotate(90deg);
        }
        details[open] summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            border-color: #667eea;
        }
        details[open] summary::before {
            color: #fff;
        }
        .empty-state {
            text-align: center;
            color: #adb5bd;
            padding: 40px;
            font-size: 16px;
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
                    <div class="entry-title">#{idx} {func_info.func_name} - {result.code_logic or '无业务逻辑描述'}</div>
                    <div class="entry-meta">
                        {func_info.file_path} |
                        行 {func_info.start_line}-{func_info.end_line} |
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
                            <div class="info-label">业务逻辑</div>
                            <div class="info-value">""" + (result.code_logic or '无业务逻辑描述') + """</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">位置</div>
                            <div class="info-value">""" + func_info.file_path + ":" + str(func_info.start_line) + "-" + str(func_info.end_line) + """</div>
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
                confidence = confidence_map.get(
                    audit.confidence.lower(), audit.confidence)

                confidence_class = "tag-danger" if audit.confidence.lower() == "high" else (
                    "tag-warning" if audit.confidence.lower() == "medium" else "tag-info")

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
    format: str = EXPORT_FORMAT_JSON
) -> str:
    """
    导出审计结果

    Args:
        results: TraceResult 列表
        output_path: 输出路径
        format: 输出格式 (EXPORT_FORMAT_JSON, EXPORT_FORMAT_HTML, EXPORT_FORMAT_SARIF, EXPORT_FORMAT_SARIF_ISSUES)

    Returns:
        输出文件路径
    """
    if format == EXPORT_FORMAT_JSON:
        return export_to_json(results, output_path)
    elif format == EXPORT_FORMAT_HTML:
        return export_to_html(results, output_path)
    elif format == EXPORT_FORMAT_SARIF:
        return export_to_sarif(results, output_path)
    elif format == EXPORT_FORMAT_SARIF_ISSUES:
        return export_to_sarif_issues_only(results, output_path)
    else:
        raise ValueError(f"不支持的格式：{format}")


def export_to_sarif(results: List['TraceResult'], output_path: str) -> str:
    """
    导出所有审计结果为 SARIF 格式

    Args:
        results: TraceResult 列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    import datetime

    # 收集所有漏洞类型以定义规则
    vulnerability_types = set()

    for result in results:
        for audit_result in result.audit_results:
            if audit_result.is_vulnerable:
                vulnerability_types.add(audit_result.vulnerability_type)

    # 创建规则定义
    rules = []
    rule_indices = {}

    # 为漏洞类型添加规则
    for i, vtype in enumerate(sorted(vulnerability_types)):
        rule_id = vtype
        rule = {
            "id": rule_id,
            "name": vtype.replace('_', ' ').title(),
            "shortDescription": {
                "text": f"{vtype.replace('_', ' ').title()} 漏洞"
            },
            "fullDescription": {
                "text": f"检测到 {vtype.replace('_', ' ').title()} 类型的安全漏洞"
            },
            "defaultConfiguration": {
                "level": "error",
                "enabled": True
            },
            "properties": {
                "category": "Security"
            }
        }
        rules.append(rule)
        rule_indices[rule_id] = i

    # 添加默认的函数分析规则
    default_rule_id = "function-analysis"
    default_rule = {
        "id": default_rule_id,
        "name": "Function Analysis",
        "shortDescription": {
            "text": "函数污点分析"
        },
        "fullDescription": {
            "text": "对函数进行污点分析和代码映射"
        },
        "defaultConfiguration": {
            "level": "note",
            "enabled": True
        },
        "properties": {
            "category": "Analysis"
        }
    }
    rules.append(default_rule)
    rule_indices[default_rule_id] = len(rules) - 1

    sarif_template = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "LLM Security Audit Tool",
                        "informationUri": "https://github.com/example/llm-security-audit",
                        "rules": rules
                    }
                },
                "results": [],
                "invocations": [
                    {
                        "startTimeUtc": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "executionSuccessful": True
                    }
                ]
            }
        ]
    }

    run = sarif_template["runs"][0]

    for result_idx, result in enumerate(results):
        func_info = result.function_info

        # 为每个函数创建一个结果项
        rule_id = "function-analysis"  # 默认规则ID
        rule_index = rule_indices[rule_id]

        sarif_result = {
            "ruleId": rule_id,
            "ruleIndex": rule_index,
            "level": "note",  # 默认为 note 级别
            "message": {
                "text": f"函数 {func_info.func_name} 的污点分析和代码映射"
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": func_info.file_path
                        },
                        "region": {
                            "startLine": func_info.start_line,
                            "endLine": func_info.end_line,
                            "snippet": {
                                "text": func_info.code_snippet
                            }
                        }
                    }
                }
            ],
            "properties": {
                "functionName": func_info.func_name,
                "codeLogic": result.code_logic,
                "codeMapCount": len(result.code_map),
                "auditResultCount": len(result.audit_results),
                "exploitResultCount": len(result.exploit_results)
            }
        }

        # 添加污点跟踪路径（codeFlows）
        if result.code_map and len(result.code_map) > 0:
            # 创建codeFlow来表示污点传播路径
            thread_flows = []

            # 添加主要的污点源（初始函数）
            primary_thread_flow = {
                "locations": [
                    {
                        "location": {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": func_info.file_path
                                },
                                "region": {
                                    "startLine": func_info.start_line,
                                    "endLine": func_info.end_line
                                }
                            },
                            "message": {
                                "text": f"外部输入点: {func_info.func_name}"
                            }
                        }
                    }
                ]
            }

            # 添加code map中的其他污点传播点
            for i, code_ctx in enumerate(result.code_map):
                primary_thread_flow["locations"].append({
                    "location": {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": code_ctx.file_path
                            },
                            "region": {
                                "startLine": code_ctx.line_start,
                                "endLine": code_ctx.line_end
                            }
                        },
                        "message": {
                            "text": f"污点传播: {code_ctx.function_name}{' (污点源)' if code_ctx.taint_source else ''}"
                        }
                    },
                    "kinds": ["call"]
                })

            thread_flows.append(primary_thread_flow)

            sarif_result["codeFlows"] = [
                {
                    "threadFlows": thread_flows
                }
            ]

        # 根据审计结果调整级别和规则
        for audit_result in result.audit_results:
            if audit_result.is_vulnerable:
                # 如果发现漏洞，创建新的结果项用于该漏洞
                vuln_rule_id = audit_result.vulnerability_type
                vuln_rule_index = rule_indices[vuln_rule_id]

                vuln_sarif_result = {
                    "ruleId": vuln_rule_id,
                    "ruleIndex": vuln_rule_index,
                    "level": "error",
                    "message": {
                        "text": f"发现 {audit_result.vulnerability_type} 漏洞: {audit_result.description}"
                    },
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": func_info.file_path
                                },
                                "region": {
                                    "startLine": func_info.start_line,
                                    "endLine": func_info.end_line,
                                    "snippet": {
                                        "text": func_info.code_snippet
                                    }
                                }
                            }
                        }
                    ],
                    "properties": {
                        "functionName": func_info.func_name,
                        "codeLogic": result.code_logic,
                        "vulnerabilityType": audit_result.vulnerability_type,
                        "confidence": audit_result.confidence,
                        "taintFlow": audit_result.taint_flow or "N/A",
                        "recommendation": audit_result.recommendation or "N/A"
                    }
                }

                # 添加污点跟踪路径（codeFlows）
                if audit_result.code_map and len(audit_result.code_map) > 0:
                    # 创建codeFlow来表示污点传播路径
                    thread_flows = []

                    # 添加主要的污点源（初始函数）
                    primary_thread_flow = {
                        "locations": [
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": func_info.file_path
                                        },
                                        "region": {
                                            "startLine": func_info.start_line,
                                            "endLine": func_info.end_line
                                        }
                                    },
                                    "message": {
                                        "text": f"外部输入点: {func_info.func_name}"
                                    }
                                }
                            }
                        ]
                    }

                    # 添加code map中的其他污点传播点
                    for j, code_ctx in enumerate(audit_result.code_map):
                        primary_thread_flow["locations"].append({
                            "location": {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": code_ctx.file_path
                                    },
                                    "region": {
                                        "startLine": code_ctx.line_start,
                                        "endLine": code_ctx.line_end
                                    }
                                },
                                "message": {
                                    "text": f"污点传播: {code_ctx.function_name}{' (污点源)' if code_ctx.taint_source else ''}"
                                }
                            },
                            "kinds": ["call"]
                        })

                    thread_flows.append(primary_thread_flow)

                    vuln_sarif_result["codeFlows"] = [
                        {
                            "threadFlows": thread_flows
                        }
                    ]

                run["results"].append(vuln_sarif_result)

        # 如果没有发现漏洞，但有漏洞利用尝试，也可以记录
        has_vulnerability = any(ar.is_vulnerable for ar in result.audit_results)
        if not has_vulnerability and result.exploit_results:
            sarif_result["level"] = "warning"

        # 总是添加函数分析结果（即使没有漏洞）
        run["results"].append(sarif_result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sarif_template, f, indent=2, ensure_ascii=False)

    return output_path


def export_to_sarif_issues_only(results: List['TraceResult'], output_path: str) -> str:
    """
    仅导出有问题的审计结果为 SARIF 格式

    Args:
        results: TraceResult 列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    import datetime

    # 收集所有漏洞类型以定义规则
    vulnerability_types = set()
    exploit_types = set()

    for result in results:
        for audit_result in result.audit_results:
            if audit_result.is_vulnerable:
                vulnerability_types.add(audit_result.vulnerability_type)

        for exploit_result in result.exploit_results:
            if exploit_result.success:
                exploit_types.add(exploit_result.vulnerability_type)

    # 创建规则定义
    rules = []
    rule_indices = {}

    # 为漏洞类型添加规则
    for i, vtype in enumerate(sorted(vulnerability_types)):
        rule_id = vtype
        rule = {
            "id": rule_id,
            "name": vtype.replace('_', ' ').title(),
            "shortDescription": {
                "text": f"{vtype.replace('_', ' ').title()} 漏洞"
            },
            "fullDescription": {
                "text": f"检测到 {vtype.replace('_', ' ').title()} 类型的安全漏洞"
            },
            "defaultConfiguration": {
                "level": "error",
                "enabled": True
            },
            "properties": {
                "category": "Security"
            }
        }
        rules.append(rule)
        rule_indices[rule_id] = i

    # 为漏洞利用类型添加规则
    for i, etype in enumerate(sorted(exploit_types)):
        rule_id = f"{etype}-exploit"
        rule = {
            "id": rule_id,
            "name": f"{etype} exploit",
            "shortDescription": {
                "text": f"{etype.replace('_', ' ').title()} 漏洞利用成功"
            },
            "fullDescription": {
                "text": f"成功利用 {etype.replace('_', ' ').title()} 类型的安全漏洞"
            },
            "defaultConfiguration": {
                "level": "error",
                "enabled": True
            },
            "properties": {
                "category": "Security"
            }
        }
        rules.append(rule)
        rule_indices[rule_id] = len(rules) - 1

    sarif_template = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "LLM Security Audit Tool - Issues Only",
                        "informationUri": "https://github.com/example/llm-security-audit",
                        "rules": rules
                    }
                },
                "results": [],
                "invocations": [
                    {
                        "startTimeUtc": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "executionSuccessful": True
                    }
                ]
            }
        ]
    }

    run = sarif_template["runs"][0]

    for result_idx, result in enumerate(results):
        func_info = result.function_info

        # 只有当审计结果显示存在漏洞时才包含在内
        has_vulnerabilities = any(
            ar.is_vulnerable for ar in result.audit_results)
        has_exploit_success = any(er.success for er in result.exploit_results)

        if has_vulnerabilities or has_exploit_success:
            # 为每个有问题的函数创建一个结果项
            for i, audit_result in enumerate(result.audit_results):
                if audit_result.is_vulnerable:
                    rule_id = audit_result.vulnerability_type  # 使用漏洞类型作为规则ID
                    sarif_result = {
                        "ruleId": rule_id,
                        "ruleIndex": rule_indices[rule_id],
                        "level": "error",
                        "message": {
                            "text": f"{audit_result.vulnerability_type}: {audit_result.description}"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": func_info.file_path
                                    },
                                    "region": {
                                        "startLine": func_info.start_line,
                                        "endLine": func_info.end_line,
                                        "snippet": {
                                            "text": func_info.code_snippet
                                        }
                                    }
                                }
                            }
                        ],
                        "properties": {
                            "functionName": func_info.func_name,
                            "codeLogic": result.code_logic,
                            "vulnerabilityType": audit_result.vulnerability_type,
                            "confidence": audit_result.confidence,
                            "taintFlow": audit_result.taint_flow or "N/A",
                            "recommendation": audit_result.recommendation or "N/A"
                        }
                    }

                    # 添加污点跟踪路径（codeFlows）
                    if audit_result.code_map and len(audit_result.code_map) > 0:
                        # 创建codeFlow来表示污点传播路径
                        thread_flows = []

                        # 添加主要的污点源（初始函数）
                        primary_thread_flow = {
                            "locations": [
                                {
                                    "location": {
                                        "physicalLocation": {
                                            "artifactLocation": {
                                                "uri": func_info.file_path
                                            },
                                            "region": {
                                                "startLine": func_info.start_line,
                                                "endLine": func_info.end_line
                                            }
                                        },
                                        "message": {
                                            "text": f"外部输入点: {func_info.func_name}"
                                        }
                                    }
                                }
                            ]
                        }

                        # 添加code map中的其他污点传播点
                        for j, code_ctx in enumerate(audit_result.code_map):
                            primary_thread_flow["locations"].append({
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": code_ctx.file_path
                                        },
                                        "region": {
                                            "startLine": code_ctx.line_start,
                                            "endLine": code_ctx.line_end
                                        }
                                    },
                                    "message": {
                                        "text": f"污点传播: {code_ctx.function_name}{' (污点源)' if code_ctx.taint_source else ''}"
                                    }
                                },
                                "kinds": ["call"]
                            })

                        thread_flows.append(primary_thread_flow)

                        sarif_result["codeFlows"] = [
                            {
                                "threadFlows": thread_flows
                            }
                        ]

                    run["results"].append(sarif_result)

            # 添加漏洞利用成功的记录
            for i, exploit_result in enumerate(result.exploit_results):
                if exploit_result.success:
                    rule_id = f"{exploit_result.vulnerability_type}-exploit"  # 使用漏洞利用类型作为规则ID
                    sarif_result = {
                        "ruleId": rule_id,
                        "ruleIndex": rule_indices[rule_id],
                        "level": "error",
                        "message": {
                            "text": f"漏洞利用成功 - {exploit_result.vulnerability_type}: {exploit_result.poc_command}"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": func_info.file_path
                                    },
                                    "region": {
                                        "startLine": func_info.start_line,
                                        "endLine": func_info.end_line,
                                        "snippet": {
                                            "text": func_info.code_snippet
                                        }
                                    }
                                }
                            }
                        ],
                        "properties": {
                            "functionName": func_info.func_name,
                            "codeLogic": result.code_logic,
                            "vulnerabilityType": exploit_result.vulnerability_type,
                            "pocCommand": exploit_result.poc_command,
                            "output": exploit_result.output,
                            "error": exploit_result.error or "N/A"
                        }
                    }

                    # 添加污点跟踪路径（codeFlows）对于exploit结果
                    if result.code_map and len(result.code_map) > 0:
                        # 创建codeFlow来表示污点传播路径
                        thread_flows = []

                        # 添加主要的污点源（初始函数）
                        primary_thread_flow = {
                            "locations": [
                                {
                                    "location": {
                                        "physicalLocation": {
                                            "artifactLocation": {
                                                "uri": func_info.file_path
                                            },
                                            "region": {
                                                "startLine": func_info.start_line,
                                                "endLine": func_info.end_line
                                            }
                                        },
                                        "message": {
                                            "text": f"外部输入点: {func_info.func_name}"
                                        }
                                    }
                                }
                            ]
                        }

                        # 添加code map中的其他污点传播点
                        for j, code_ctx in enumerate(result.code_map):
                            primary_thread_flow["locations"].append({
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": code_ctx.file_path
                                        },
                                        "region": {
                                            "startLine": code_ctx.line_start,
                                            "endLine": code_ctx.line_end
                                        }
                                    },
                                    "message": {
                                        "text": f"污点传播: {code_ctx.function_name}{' (污点源)' if code_ctx.taint_source else ''}"
                                    }
                                },
                                "kinds": ["call"]
                            })

                        thread_flows.append(primary_thread_flow)

                        sarif_result["codeFlows"] = [
                            {
                                "threadFlows": thread_flows
                            }
                        ]

                    run["results"].append(sarif_result)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sarif_template, f, indent=2, ensure_ascii=False)

    return output_path
