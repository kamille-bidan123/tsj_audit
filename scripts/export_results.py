#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计结果导出工具

此脚本用于将审计检查点合并并导出为多种格式：
- JSON: 完整的审计结果
- HTML: 可视化报告
- MARKDOWN: 每个函数一个 Markdown 审计报告，分别输出全量目录和有漏洞目录
- SARIF: 静态分析结果交换格式
- SARIF-ISSUES: 仅包含问题的 SARIF 格式

用法:
    python export_results.py <output_dir>

示例:
    python export_results.py ./audit_results
    python export_results.py ./audit_results --debug
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from utils.export_utils import merge_checkpoints_and_export
except ImportError as e:
    print(f"错误: 无法导入导出工具模块: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='审计结果导出工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python export_results.py ./audit_results              # 导出审计结果
    python export_results.py ./audit_results --debug      # 调试模式导出
        """,
    )
    parser.add_argument('output_dir', help='输出目录路径，应包含checkpoints子目录')
    parser.add_argument('--debug', '-d', action='store_true', help='启用调试模式')

    args = parser.parse_args()

    # 检查输出目录是否存在
    if not os.path.isdir(args.output_dir):
        print(f"错误: 输出目录 '{args.output_dir}' 不存在", file=sys.stderr)
        sys.exit(1)

    # 检查输出目录中是否有 checkpoints 子目录
    checkpoints_dir = Path(args.output_dir) / "checkpoints"
    if not checkpoints_dir.exists():
        print(f"警告: 目录 '{checkpoints_dir}' 不存在，这通常是存储检查点的子目录", file=sys.stderr)
        print(f"继续执行，但可能找不到要导出的审计结果。", file=sys.stderr)

    try:
        # 调用导出函数
        results = merge_checkpoints_and_export(args.output_dir, debug=args.debug)

        print(f"\n导出完成! 找到了 {len(results)} 个函数的审计结果。")
        print(f"输出文件已保存到: {args.output_dir}")
        print("- JSON 格式: trace_results_YYYYMMDD_HHMMSS.json")
        print("- HTML 格式: trace_results_YYYYMMDD_HHMMSS.html")
        print("- Markdown 格式: trace_results_YYYYMMDD_HHMMSS_markdown/ (all/, vulnerable/)")
        print("- SARIF 格式: trace_results_YYYYMMDD_HHMMSS.sarif")
        print("- SARIF 问题格式: trace_results_YYYYMMDD_HHMMSS_issues.sarif")

    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
