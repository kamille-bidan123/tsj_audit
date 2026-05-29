#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行参数解析模块

与 config 模块配合使用：
1. config 模块负责从 .env 加载配置
2. cli 模块负责解析命令行参数并覆盖配置
"""

import argparse
from config import init_settings


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(
        description="代码审计 Agent 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用
  python main.py

  # 指定配置文件
  python main.py --config configs/opencode.env

  # 调试模式
  python main.py --debug

  # 断点续审（从中间停止处恢复审计）
  python main.py --resume

配置文件:
  程序会尝试从以下位置加载 .env 文件 (优先级从高到低):
  1. --config 指定的文件
  2. 当前工作目录 (./.env)
  3. 用户主目录 (~/.env)
  命令行参数会覆盖配置文件中的值
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="显式指定 .env 风格配置文件；命令行参数仍会覆盖该文件",
    )

    # ========== Runtime 配置 ==========
    api_group = parser.add_argument_group("Runtime 配置")

    api_group.add_argument(
        "--agent-runtime",
        type=str,
        choices=["opencode", "codex", "claudecode"],
        default=None,
        help="Agent 内层 runtime（默认从配置文件读取）",
    )

    api_group.add_argument(
        "--opencode-base-url",
        type=str,
        default=None,
        help="opencode serve REST API 地址（默认从配置文件读取）",
    )

    api_group.add_argument(
        "--opencode-provider-id",
        type=str,
        default=None,
        help="opencode providerID（默认从配置文件读取）",
    )

    api_group.add_argument(
        "--opencode-model-id",
        type=str,
        default=None,
        help="opencode modelID（默认从配置文件读取）",
    )

    api_group.add_argument(
        "--opencode-structured-output-mode",
        type=str,
        choices=["auto", "json_schema", "prompt"],
        default=None,
        help="opencode 结构化输出模式（默认 auto，启动时探测兼容性）",
    )

    # ========== 功能开关 ==========
    feature_group = parser.add_argument_group("功能开关")

    feature_group.add_argument(
        "--disable-exploit",
        action="store_true",
        default=None,
        help="禁用 ExploitAgent（不生成 PoC）",
    )

    feature_group.add_argument(
        "--enable-fallback-audit",
        action="store_true",
        default=None,
        help="启用兜底审计（正常漏洞类型完成后，额外审计已有类型以外的安全问题）",
    )

    feature_group.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="启用调试模式（输出详细信息）",
    )

    feature_group.add_argument(
        "--resume",
        action="store_true",
        default=None,
        help="从输出目录的中间信息恢复审计",
    )

    feature_group.add_argument(
        "--scan",
        type=str,
        default=None,
        help="指定起始扫描脚本（仅脚本，不接收 JSON）",
    )

    feature_group.add_argument(
        "--entry",
        type=str,
        default=None,
        help="指定 EntrySpec JSON 入口文件",
    )

    feature_group.add_argument(
        "--attack-surface-skill",
        type=str,
        default=None,
        help="指定攻击面 skill 名，自动发现该攻击面的所有入口函数并审计",
    )

    # ========== 项目配置 ==========
    project_group = parser.add_argument_group("项目配置")

    project_group.add_argument(
        "--project-path",
        type=str,
        default=None,
        help="待审计的项目路径",
    )

    # ========== 审计配置 ==========
    audit_group = parser.add_argument_group("审计配置")

    audit_group.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="审计报告输出目录",
    )

    audit_group.add_argument(
        "--target-base-url",
        type=str,
        default=None,
        help="PoC 远程 URL 目标（默认从配置读取）",
    )

    audit_group.add_argument(
        "--audit-types",
        type=str,
        default=None,
        help="额外显式启用的审计类型，逗号分隔；会追加到攻击面 skill 绑定的 required_audit_types",
    )

    args = parser.parse_args()

    # 将命令行参数应用到配置
    cli_dict = vars(args)
    config = init_settings(cli_dict)

    return config
