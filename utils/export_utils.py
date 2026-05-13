#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出工具 - 生成各种格式的审计报告
"""

from typing import List
import json
import datetime
import re

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
    stats = _build_report_stats(results)
    cards = "\n".join(_render_function_card(result, idx) for idx, result in enumerate(results, 1))
    type_filters = _render_vulnerability_type_filters(results)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码安全审计报告</title>
    <style>
        :root {{
            --bg: #08111f;
            --panel: rgba(12, 24, 40, 0.86);
            --panel-strong: #0e1c2f;
            --ink: #e8f1ff;
            --muted: #8ea3bd;
            --line: rgba(148, 163, 184, 0.24);
            --accent: #38d5c8;
            --amber: #f5b84b;
            --danger: #ff5c7a;
            --ok: #4ade80;
            --code: #050a12;
            --shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
        }}
        * {{ box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            margin: 0;
            color: var(--ink);
            font-family: "Aptos", "SF Pro Display", "Segoe UI", "PingFang SC", sans-serif;
            background:
                radial-gradient(circle at 12% 8%, rgba(56, 213, 200, 0.22), transparent 28rem),
                radial-gradient(circle at 86% 0%, rgba(245, 184, 75, 0.18), transparent 30rem),
                linear-gradient(135deg, #07101d 0%, #0a1626 48%, #101726 100%);
            min-height: 100vh;
        }}
        body::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
            background-size: 38px 38px;
            mask-image: linear-gradient(to bottom, black, transparent 80%);
        }}
        .report-shell {{
            width: min(1440px, calc(100% - 40px));
            margin: 0 auto;
            padding: 34px 0 56px;
        }}
        .hero {{
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.6fr);
            gap: 24px;
            align-items: stretch;
            margin-bottom: 24px;
        }}
        .hero-main, .status-panel, .toolbar, .function-card {{
            border: 1px solid var(--line);
            background: linear-gradient(145deg, rgba(15, 30, 50, 0.92), rgba(8, 17, 31, 0.74));
            box-shadow: var(--shadow);
            backdrop-filter: blur(18px);
        }}
        .hero-main {{
            border-radius: 30px;
            padding: 34px;
            position: relative;
            overflow: hidden;
        }}
        .hero-main::after {{
            content: "";
            position: absolute;
            width: 360px;
            height: 360px;
            right: -130px;
            top: -150px;
            border-radius: 999px;
            border: 1px solid rgba(56, 213, 200, 0.34);
            box-shadow: inset 0 0 80px rgba(56, 213, 200, 0.08);
        }}
        .eyebrow {{
            color: var(--accent);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            margin-bottom: 18px;
        }}
        h1 {{
            margin: 0;
            font-size: clamp(36px, 5vw, 72px);
            line-height: 0.95;
            letter-spacing: -0.06em;
        }}
        .hero-subtitle {{
            color: var(--muted);
            max-width: 780px;
            margin: 22px 0 0;
            font-size: 16px;
        }}
        .status-panel {{
            border-radius: 30px;
            padding: 24px;
        }}
        .panel-title {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            color: #c9d8ea;
            font-size: 14px;
            font-weight: 800;
            margin-bottom: 18px;
        }}
        .status-list {{
            display: grid;
            gap: 14px;
        }}
        .status-row {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--line);
            color: var(--muted);
            font-size: 13px;
        }}
        .status-row strong {{ color: var(--ink); font-weight: 800; text-align: right; }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 14px;
            margin: 24px 0;
        }}
        .metric {{
            min-height: 112px;
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 18px;
            background: rgba(9, 19, 33, 0.72);
        }}
        .metric-label {{
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
        }}
        .metric-value {{
            margin-top: 10px;
            font-size: 34px;
            font-weight: 900;
            letter-spacing: -0.05em;
        }}
        .metric.danger .metric-value {{ color: var(--danger); }}
        .metric.warning .metric-value {{ color: var(--amber); }}
        .metric.ok .metric-value {{ color: var(--ok); }}
        .toolbar {{
            position: sticky;
            top: 0;
            z-index: 10;
            display: grid;
            grid-template-columns: minmax(260px, 1fr);
            gap: 12px;
            align-items: center;
            border-radius: 22px;
            padding: 14px;
            margin: 24px 0;
        }}
        .search-input {{
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 16px;
            background: rgba(4, 10, 18, 0.7);
            color: var(--ink);
            padding: 14px 16px;
            outline: none;
            font-size: 14px;
        }}
        .search-input:focus {{
            border-color: rgba(56, 213, 200, 0.78);
            box-shadow: 0 0 0 4px rgba(56, 213, 200, 0.12);
        }}
        .filter-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            justify-content: flex-start;
        }}
        .filter-row {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 10px;
            align-items: center;
        }}
        .filter-label {{
            color: var(--muted);
            font-size: 12px;
            font-weight: 900;
            white-space: nowrap;
        }}
        .filter-button {{
            border: 1px solid var(--line);
            border-radius: 999px;
            color: var(--muted);
            background: rgba(255, 255, 255, 0.04);
            padding: 10px 13px;
            cursor: pointer;
            font-weight: 800;
        }}
        .filter-button.active, .filter-button:hover {{
            color: #061018;
            background: var(--accent);
            border-color: var(--accent);
        }}
        .function-list {{
            display: grid;
            gap: 18px;
        }}
        .function-card {{
            border-radius: 26px;
            overflow: hidden;
            animation: rise-in 0.45s ease both;
        }}
        .function-card[hidden] {{ display: none; }}
        .function-header {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 22px;
            padding: 22px;
            cursor: pointer;
        }}
        .function-title {{
            margin: 0;
            font-size: 22px;
            letter-spacing: -0.03em;
            word-break: break-word;
        }}
        .function-meta {{
            color: var(--muted);
            margin-top: 8px;
            font-size: 13px;
            word-break: break-all;
        }}
        .logic {{
            color: #c2d2e5;
            margin-top: 14px;
            max-width: 980px;
        }}
        .markdown-body {{
            display: grid;
            gap: 8px;
        }}
        .markdown-body h1, .markdown-body h2, .markdown-body h3 {{
            margin: 0;
            color: #f7fbff;
            letter-spacing: -0.03em;
        }}
        .markdown-body h1 {{ font-size: 22px; }}
        .markdown-body h2 {{ font-size: 19px; }}
        .markdown-body h3 {{ font-size: 16px; }}
        .markdown-body p {{
            margin: 0;
        }}
        .markdown-body ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .markdown-body li {{
            margin: 3px 0;
        }}
        .markdown-body code {{
            border: 1px solid rgba(56, 213, 200, 0.28);
            border-radius: 7px;
            background: rgba(56, 213, 200, 0.10);
            color: #b7fff8;
            padding: 1px 6px;
            font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
            font-size: 0.92em;
        }}
        .markdown-body pre {{
            margin: 0;
        }}
        .markdown-body pre code {{
            display: block;
            border-color: rgba(148, 163, 184, 0.20);
            background: var(--code);
            color: #d8e6f7;
            padding: 14px;
            overflow-x: auto;
            white-space: pre-wrap;
        }}
        .risk-pill, .tag {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 900;
            white-space: nowrap;
        }}
        .risk-pill.critical, .tag-danger {{ background: rgba(255, 92, 122, 0.16); color: #ff9aad; border: 1px solid rgba(255, 92, 122, 0.36); }}
        .risk-pill.warning, .tag-warning {{ background: rgba(245, 184, 75, 0.16); color: #ffd08a; border: 1px solid rgba(245, 184, 75, 0.38); }}
        .risk-pill.low, .tag-info {{ background: rgba(56, 213, 200, 0.14); color: #8cf0e8; border: 1px solid rgba(56, 213, 200, 0.34); }}
        .risk-pill.clean, .tag-success {{ background: rgba(74, 222, 128, 0.14); color: #a5f3bc; border: 1px solid rgba(74, 222, 128, 0.32); }}
        .function-body {{
            display: none;
            padding: 0 22px 24px;
            border-top: 1px solid var(--line);
        }}
        .function-card.expanded .function-body {{ display: block; }}
        .section {{
            margin-top: 22px;
            padding-top: 2px;
        }}
        .section-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 0 0 14px;
            color: #f6fbff;
            font-size: 15px;
            font-weight: 900;
            letter-spacing: 0.02em;
        }}
        .section-title::before {{
            content: "";
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: var(--accent);
            box-shadow: 0 0 18px rgba(56, 213, 200, 0.85);
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }}
        .info-item, .audit-card, .exploit-card {{
            border: 1px solid var(--line);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.035);
            padding: 15px;
        }}
        .info-label {{
            color: var(--muted);
            font-size: 11px;
            font-weight: 900;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}
        .info-value {{
            margin-top: 6px;
            color: var(--ink);
            word-break: break-word;
        }}
        .code-block {{
            margin: 12px 0 0;
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 16px;
            background: var(--code);
            color: #d8e6f7;
            overflow-x: auto;
            padding: 16px;
            font: 13px/1.55 "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        details {{
            margin-top: 12px;
        }}
        summary {{
            cursor: pointer;
            color: #d8e6f7;
            font-weight: 850;
        }}
        .timeline {{
            position: relative;
            display: grid;
            gap: 14px;
            margin-left: 9px;
        }}
        .timeline::before {{
            content: "";
            position: absolute;
            top: 8px;
            bottom: 8px;
            left: 8px;
            width: 1px;
            background: linear-gradient(var(--accent), rgba(56, 213, 200, 0));
        }}
        .timeline-item {{
            position: relative;
            padding-left: 34px;
        }}
        .timeline-item::before {{
            content: "";
            position: absolute;
            left: 0;
            top: 5px;
            width: 16px;
            height: 16px;
            border-radius: 999px;
            background: var(--panel-strong);
            border: 2px solid var(--accent);
        }}
        .timeline-card {{
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 16px;
            background: rgba(8, 17, 31, 0.62);
        }}
        .timeline-head, .audit-head, .exploit-head {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            gap: 10px;
            align-items: center;
        }}
        .timeline-name, .audit-name, .exploit-name {{
            font-weight: 950;
            word-break: break-word;
        }}
        .muted {{
            color: var(--muted);
        }}
        .audit-list, .exploit-list {{
            display: grid;
            gap: 12px;
        }}
        .audit-description {{
            margin: 14px 0 0;
            color: #d5e2f4;
        }}
        .empty-state {{
            border: 1px dashed var(--line);
            border-radius: 18px;
            color: var(--muted);
            padding: 24px;
            text-align: center;
        }}
        @keyframes rise-in {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        @media (max-width: 980px) {{
            .hero, .toolbar {{ grid-template-columns: 1fr; }}
            .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
            .filter-group {{ justify-content: flex-start; }}
        }}
        @media (max-width: 620px) {{
            .report-shell {{ width: min(100% - 24px, 1440px); padding-top: 18px; }}
            .hero-main, .status-panel {{ border-radius: 22px; padding: 22px; }}
            .summary-grid {{ grid-template-columns: 1fr; }}
            .function-header {{ grid-template-columns: 1fr; }}
            .filter-row {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <main class="report-shell">
        <section class="hero">
            <div class="hero-main">
                <div class="eyebrow">Security Audit Report</div>
                <h1>代码安全审计报告</h1>
                <p class="hero-subtitle">面向函数入口的代码理解、漏洞类型调度与 PoC 验证结果。报告由本地 checkpoint 合并生成，适合归档、复盘和人工二次确认。</p>
            </div>
            <aside class="status-panel">
                <div class="panel-title"><span>报告状态</span><span>{_escape_html(generated_at)}</span></div>
                <div class="status-list">
                    <div class="status-row"><span>编排方式</span><strong>TraceAgent → AuditSpec → Runtime</strong></div>
                    <div class="status-row"><span>Runtime</span><strong>Codex / OpenCode / ClaudeCode</strong></div>
                    <div class="status-row"><span>工具边界</span><strong>tags/cscope MCP 外置</strong></div>
                    <div class="status-row"><span>失败降级 / 验证状态</span><strong>低置信度保守输出</strong></div>
                </div>
            </aside>
        </section>

        {_render_summary(stats)}

        <section class="toolbar" aria-label="报告过滤器">
            <input id="reportSearch" class="search-input" type="search" placeholder="搜索函数名、文件、漏洞类型、描述..." oninput="filterReport()">
            <div class="filter-row">
                <div class="filter-label">风险</div>
                <div class="filter-group" aria-label="风险过滤">
                    <button class="filter-button active" type="button" data-filter="all" onclick="setRiskFilter(this)">全部</button>
                    <button class="filter-button" type="button" data-filter="critical" onclick="setRiskFilter(this)">高危</button>
                    <button class="filter-button" type="button" data-filter="warning" onclick="setRiskFilter(this)">中危</button>
                    <button class="filter-button" type="button" data-filter="low" onclick="setRiskFilter(this)">低危</button>
                    <button class="filter-button" type="button" data-filter="clean" onclick="setRiskFilter(this)">未发现</button>
                </div>
            </div>
            <div class="filter-row">
                <div class="filter-label">漏洞类型</div>
                <div class="filter-group type-filter-group" aria-label="漏洞类型过滤">
                    <button class="filter-button active" type="button" data-type-filter="all" onclick="setTypeFilter(this)">全部问题类型</button>
                    {type_filters}
                </div>
            </div>
        </section>

        <section class="function-list" id="functionList">
            {cards or '<div class="empty-state">暂无审计结果</div>'}
        </section>
    </main>

    <script>
        let activeRisk = 'all';
        let activeType = 'all';

        function toggleEntry(header) {{
            const entry = header.closest('.function-card');
            entry.classList.toggle('expanded');
        }}

        function setRiskFilter(button) {{
            activeRisk = button.dataset.filter;
            document.querySelectorAll('[data-filter]').forEach((item) => item.classList.remove('active'));
            button.classList.add('active');
            filterReport();
        }}

        function setTypeFilter(button) {{
            activeType = button.dataset.typeFilter;
            document.querySelectorAll('[data-type-filter]').forEach((item) => item.classList.remove('active'));
            button.classList.add('active');
            filterReport();
        }}

        function filterReport() {{
            const query = document.getElementById('reportSearch').value.trim().toLowerCase();
            document.querySelectorAll('.function-card').forEach((card) => {{
                const matchesQuery = !query || card.dataset.search.includes(query);
                const matchesRisk = activeRisk === 'all' || card.dataset.risk === activeRisk;
                const vulnTypes = card.dataset.vulnTypes ? card.dataset.vulnTypes.split('|') : [];
                const matchesType = activeType === 'all' || vulnTypes.includes(activeType);
                card.hidden = !(matchesQuery && matchesRisk && matchesType);
            }});
        }}
    </script>
</body>
</html>
"""


def _build_report_stats(results: List['TraceResult']) -> dict:
    vulnerable_findings = []
    exploit_success = 0
    for result in results:
        vulnerable_findings.extend([audit for audit in result.audit_results if audit.is_vulnerable])
        exploit_success += sum(1 for exploit in result.exploit_results if exploit.success)

    vulnerable_functions = sum(1 for result in results if any(audit.is_vulnerable for audit in result.audit_results))
    return {
        "functions": len(results),
        "vulnerable_functions": vulnerable_functions,
        "vulnerable_findings": len(vulnerable_findings),
        "high": sum(1 for audit in vulnerable_findings if audit.confidence.lower() == "high"),
        "medium": sum(1 for audit in vulnerable_findings if audit.confidence.lower() == "medium"),
        "low": sum(1 for audit in vulnerable_findings if audit.confidence.lower() == "low"),
        "exploit_success": exploit_success,
        "code_contexts": sum(len(result.code_map) for result in results),
    }


def _render_summary(stats: dict) -> str:
    metrics = [
        ("审计函数", stats["functions"], ""),
        ("漏洞函数", stats["vulnerable_functions"], "danger"),
        ("漏洞发现", stats["vulnerable_findings"], "danger"),
        ("高置信度", stats["high"], "danger"),
        ("中置信度", stats["medium"], "warning"),
        ("PoC 成功", stats["exploit_success"], "ok"),
    ]
    items = "\n".join(
        f"""
            <div class="metric {css_class}">
                <div class="metric-label">{_escape_html(label)}</div>
                <div class="metric-value">{value}</div>
            </div>
        """
        for label, value, css_class in metrics
    )
    return f"""<section class="summary-grid" aria-label="审计摘要">{items}</section>"""


def _render_vulnerability_type_filters(results: List['TraceResult']) -> str:
    vulnerable_types = sorted({
        audit.vulnerability_type
        for result in results
        for audit in result.audit_results
        if audit.is_vulnerable and audit.vulnerability_type
    })
    if not vulnerable_types:
        return '<button class="filter-button" type="button" disabled>暂无问题类型</button>'
    return "\n".join(
        f'<button class="filter-button" type="button" data-type-filter="{_escape_attr(vuln_type)}" onclick="setTypeFilter(this)">{_escape_html(vuln_type)}</button>'
        for vuln_type in vulnerable_types
    )


def _render_function_card(result: 'TraceResult', idx: int) -> str:
    func_info = result.function_info
    risk, risk_label = _risk_level(result)
    location = f"{func_info.file_path}:{func_info.start_line}-{func_info.end_line}"
    vulnerable_types = sorted({
        audit.vulnerability_type
        for audit in result.audit_results
        if audit.is_vulnerable and audit.vulnerability_type
    })
    search_text = " ".join(
        [
            func_info.func_name,
            func_info.file_path,
            result.code_logic or "",
            " ".join(audit.vulnerability_type for audit in result.audit_results),
            " ".join(audit.description for audit in result.audit_results),
        ]
    ).lower()
    audit_count = len(result.audit_results)
    vulnerable_count = sum(1 for audit in result.audit_results if audit.is_vulnerable)

    return f"""
        <article class="function-card" id="entry-{idx}" data-risk="{_escape_attr(risk)}" data-vuln-types="{_escape_attr('|'.join(vulnerable_types))}" data-search="{_escape_attr(search_text)}">
            <header class="function-header" onclick="toggleEntry(this)">
                <div>
                    <h2 class="function-title">#{idx} {_escape_html(func_info.func_name)}</h2>
                    <div class="function-meta">{_escape_html(location)} · Skill {_escape_html(func_info.skill or '未指定')}</div>
                    {_render_code_logic(result.code_logic)}
                </div>
                <div>
                    <span class="risk-pill {risk}">{_escape_html(risk_label)}</span>
                </div>
            </header>
            <div class="function-body">
                <section class="section">
                    <h3 class="section-title">函数概览</h3>
                    <div class="info-grid">
                        <div class="info-item"><div class="info-label">审计类型数</div><div class="info-value">{audit_count}</div></div>
                        <div class="info-item"><div class="info-label">漏洞命中数</div><div class="info-value">{vulnerable_count}</div></div>
                        <div class="info-item"><div class="info-label">Code Map 节点</div><div class="info-value">{len(result.code_map)}</div></div>
                        <div class="info-item"><div class="info-label">PoC 结果</div><div class="info-value">{len(result.exploit_results)} 条</div></div>
                    </div>
                    <details>
                        <summary>查看入口代码</summary>
                        <div class="code-block">{_escape_html(func_info.code_snippet)}</div>
                    </details>
                </section>
                {_render_code_map(result.code_map)}
                {_render_audit_results(result.audit_results)}
                {_render_exploit_results(result.exploit_results)}
            </div>
        </article>
    """


def _render_code_logic(code_logic: str) -> str:
    content = code_logic or "无业务逻辑描述"
    return f'<div class="logic markdown-body">{_render_markdown(content)}</div>'


def _render_markdown(text: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code_block = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_render_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            items = "".join(f"<li>{item}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                blocks.append(f"<pre><code>{_escape_html(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                flush_paragraph()
                flush_list()
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_render_inline_markdown(heading.group(2))}</h{level}>")
            continue

        item = re.match(r"^[-*]\s+(.+)$", stripped)
        if item:
            flush_paragraph()
            list_items.append(_render_inline_markdown(item.group(1)))
            continue

        flush_list()
        paragraph.append(stripped)

    if in_code_block:
        blocks.append(f"<pre><code>{_escape_html(chr(10).join(code_lines))}</code></pre>")
    flush_paragraph()
    flush_list()
    return "".join(blocks)


def _render_inline_markdown(text: str) -> str:
    escaped = _escape_html(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _render_code_map(code_map: list) -> str:
    if not code_map:
        content = '<div class="empty-state">暂无代码映射数据</div>'
    else:
        content = '<div class="timeline">'
        for ctx in code_map:
            entry_tag = '<span class="tag tag-info">入口</span>' if ctx.is_entry_point else '<span class="tag">关联</span>'
            location = f"{ctx.file_path}:{ctx.line_start}-{ctx.line_end}"
            content += f"""
                <div class="timeline-item">
                    <div class="timeline-card">
                        <div class="timeline-head">
                            <div class="timeline-name">{_escape_html(ctx.function_name)}</div>
                            <div>{entry_tag} <span class="tag tag-info">{_escape_html(location)}</span></div>
                        </div>
                        <div class="info-grid" style="margin-top: 12px;">
                            <div class="info-item"><div class="info-label">污染源</div><div class="info-value">{_escape_html(ctx.taint_source or '无')}</div></div>
                            <div class="info-item"><div class="info-label">污染路径</div><div class="info-value">{_escape_html(ctx.taint_path or '无')}</div></div>
                        </div>
                        <details>
                            <summary>查看代码</summary>
                            <div class="code-block">{_escape_html(ctx.code_snippet)}</div>
                        </details>
                    </div>
                </div>
            """
        content += "</div>"

    return f"""
        <section class="section">
            <h3 class="section-title">Code Map Timeline</h3>
            {content}
        </section>
    """


def _render_audit_results(audit_results: list) -> str:
    if not audit_results:
        content = '<div class="empty-state">暂无漏洞审计结果</div>'
    else:
        content = '<div class="audit-list">'
        for audit in audit_results:
            status_class = "tag-danger" if audit.is_vulnerable else "tag-success"
            status_label = "存在漏洞" if audit.is_vulnerable else "未发现"
            confidence_label = _confidence_label(audit.confidence)
            confidence_class = _confidence_class(audit.confidence)
            content += f"""
                <article class="audit-card">
                    <div class="audit-head">
                        <div class="audit-name">{_escape_html(audit.vulnerability_type)}</div>
                        <div>
                            <span class="tag {status_class}">{status_label}</span>
                            <span class="tag {confidence_class}">置信度：{_escape_html(confidence_label)}</span>
                        </div>
                    </div>
                    <p class="audit-description">{_escape_html(audit.description)}</p>
                    {_render_optional_code_block('污点流', audit.taint_flow)}
                    {_render_optional_code_block('修复建议', audit.recommendation)}
                    {_render_audit_contexts(audit.code_map)}
                </article>
            """
        content += "</div>"

    return f"""
        <section class="section">
            <h3 class="section-title">漏洞审计结果</h3>
            {content}
        </section>
    """


def _render_audit_contexts(code_map: list) -> str:
    if not code_map:
        return ""
    items = ""
    for ctx in code_map:
        location = f"{ctx.file_path}:{ctx.line_start}-{ctx.line_end}"
        items += f"""
            <div class="timeline-card" style="margin-top: 10px;">
                <div class="timeline-head">
                    <div class="timeline-name">{_escape_html(ctx.function_name)}</div>
                    <span class="tag tag-info">{_escape_html(location)}</span>
                </div>
                <div class="code-block">{_escape_html(ctx.code_snippet)}</div>
            </div>
        """
    return f"""
        <details>
            <summary>相关代码上下文</summary>
            {items}
        </details>
    """


def _render_exploit_results(exploit_results: list) -> str:
    if not exploit_results:
        content = '<div class="empty-state">暂无漏洞利用结果</div>'
    else:
        content = '<div class="exploit-list">'
        for exploit in exploit_results:
            status_class = "tag-danger" if exploit.success else "tag-warning"
            status_label = "利用成功" if exploit.success else "利用失败"
            content += f"""
                <article class="exploit-card">
                    <div class="exploit-head">
                        <div class="exploit-name">{_escape_html(exploit.vulnerability_type)}</div>
                        <span class="tag {status_class}">{status_label}</span>
                    </div>
                    {_render_optional_code_block('PoC 命令', exploit.poc_command)}
                    {_render_optional_code_block('执行输出', exploit.output)}
                    {_render_optional_code_block('错误信息', exploit.error)}
                </article>
            """
        content += "</div>"

    return f"""
        <section class="section">
            <h3 class="section-title">漏洞利用结果</h3>
            {content}
        </section>
    """


def _render_optional_code_block(title: str, value: str | None) -> str:
    if not value:
        return ""
    return f"""
        <details open>
            <summary>{_escape_html(title)}</summary>
            <div class="code-block">{_escape_html(value)}</div>
        </details>
    """


def _risk_level(result: 'TraceResult') -> tuple[str, str]:
    vulnerable = [audit for audit in result.audit_results if audit.is_vulnerable]
    if any(audit.confidence.lower() == "high" for audit in vulnerable):
        return "critical", "高危"
    if any(audit.confidence.lower() == "medium" for audit in vulnerable):
        return "warning", "中危"
    if vulnerable:
        return "low", "低危"
    return "clean", "未发现"


def _confidence_label(confidence: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(confidence.lower(), confidence)


def _confidence_class(confidence: str) -> str:
    if confidence.lower() == "high":
        return "tag-danger"
    if confidence.lower() == "medium":
        return "tag-warning"
    return "tag-info"


def _escape_attr(text: str) -> str:
    return _escape_html(text).replace("\n", " ").replace("\r", " ")


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
