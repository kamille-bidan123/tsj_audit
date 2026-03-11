#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行参数解析模块

与 config 模块配合使用：
1. config 模块负责从 .env 加载配置
2. cli 模块负责解析命令行参数并覆盖配置
"""

import argparse
from typing import Optional

from config import init_settings, get_config, set_config, Config


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""

    parser = argparse.ArgumentParser(
        description="代码审计 Agent 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用
  python main.py --api-key sk-xxx

  # 使用本地 Docker 容器
  python main.py --api-key sk-xxx --enable-docker --docker-container my_container

  # 调试模式
  python main.py --api-key sk-xxx --debug

配置文件:
  程序会尝试从以下位置加载 .env 文件 (优先级从高到低):
  1. 当前工作目录 (./.env)
  2. 用户主目录 (~/.env)
  命令行参数会覆盖配置文件中的值
        """,
    )

    # ========== API 配置 ==========
    api_group = parser.add_argument_group("API 配置")

    api_group.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="API 基础 URL (默认从配置文件读取)",
    )

    api_group.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API 密钥 (必需，可从 .env 或命令行指定)",
    )

    api_group.add_argument(
        "--model-name",
        type=str,
        default=None,
        help="模型名称 (默认从配置文件读取)",
    )

    # ========== 功能开关 ==========
    feature_group = parser.add_argument_group("功能开关")

    feature_group.add_argument(
        "--enable-docker",
        action="store_true",
        default=None,
        help="启用 Docker 模式（代码在容器内执行）",
    )

    feature_group.add_argument(
        "--enable-lsp",
        action="store_true",
        default=None,
        help="启用 LSP 语言服务器支持",
    )

    feature_group.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="启用调试模式（输出详细信息）",
    )

    # ========== Docker 配置 ==========
    docker_group = parser.add_argument_group("Docker 配置（仅在 --enable-docker 时有效）")

    docker_group.add_argument(
        "--docker-container",
        type=str,
        default=None,
        help="Docker 容器 ID 或名称",
    )

    docker_group.add_argument(
        "--docker-workdir",
        type=str,
        default=None,
        help="容器内工作目录",
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
        "--project-type",
        type=str,
        default=None,
        help="项目类型",
    )

    audit_group.add_argument(
        "--attack-surface",
        type=str,
        default=None,
        help="攻击面类型",
    )

    args = parser.parse_args()

    # 将命令行参数应用到配置
    cli_dict = vars(args)
    config = init_settings(cli_dict)

    # 验证必需参数
    if not config.api_key:
        parser.error("--api-key 是必需的，可以通过命令行或.env 文件提供")

    return config


def get_global_config() -> dict:
    """
    获取全局配置字典

    为了与其他模块兼容，返回配置字典格式。

    Returns:
        dict 配置字典
    """
    return get_config().model_dump()


def set_global_config(config_dict: dict):
    """
    设置全局配置

    Args:
        config_dict: 配置字典
    """
    config = Config(**config_dict)
    set_config(config)


def get_config_object() -> Config:
    """
    获取配置对象

    Returns:
        Config 配置对象
    """
    return get_config()
