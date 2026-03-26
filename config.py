#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块 - 使用 pydantic-settings 管理配置

所有配置从以下来源加载（优先级从高到低）：
1. 命令行参数
2. .env 文件（当前工作目录或用户主目录）
3. 默认值
"""

import sys
from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """
    全局配置类

    配置字段说明:
    - API 配置：base_url, api_key, model_name
    - 功能开关：enable_lsp, debug
    - 项目配置：project_path, scan, max_turns, output_dir
    """

    # API 配置
    base_url: str = Field(
        default="https://api.anthropic.com/v1",
        description="API 基础 URL"
    )
    api_key: str = Field(
        default="",
        description="API 密钥"
    )
    model_name: str = Field(
        default="claude-sonnet-4-6",
        description="模型名称"
    )

    # 功能开关
    enable_lsp: bool = Field(
        default=False,
        description="启用 LSP 语言服务器"
    )
    disable_exploit: bool = Field(
        default=False,
        description="禁用 ExploitAgent"
    )
    debug: bool = Field(
        default=False,
        description="启用调试模式"
    )

    # 断点续审配置
    resume: bool = Field(
        default=False,
        description="从输出目录的中间信息恢复审计"
    )

    # 项目配置
    project_path: str = Field(
        default=".",
        description="项目路径"
    )

    scan: str = Field(
        default="",
        description="起始扫描脚本路径"
    )
    max_turns: int = Field(
        default=50,
        description="审计最大轮数"
    )
    output_dir: str = Field(
        default="output",
        description="审计报告输出目录"
    )

    # Skills 配置
    skills_path: str = Field(
        default="skills",
        description="Skills 目录路径"
    )

    # 命令行参数（用于传递 argparse 解析结果）
    _cli_args: dict | None = None

    model_config = SettingsConfigDict(
        env_file=None,  # 不自动加载 .env，由 find_env_file() 处理
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    def __init__(self, **kwargs):
        # 保存命令行参数
        cli_args = kwargs.pop("_cli_args", None)
        if cli_args:
            self._cli_args = cli_args
            # 将命令行参数合并到 kwargs
            for key, value in cli_args.items():
                if key != "_cli_args" and value is not None:
                    kwargs[key] = value

        super().__init__(**kwargs)


def find_env_file() -> Path:
    """
    查找 .env 文件

    查找顺序:
    1. 当前工作目录 (cwd)
    2. 用户主目录 (~)

    Returns:
        .env 文件路径
    """
    # 1. 当前工作目录
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    # 2. 用户主目录
    home_env = Path.home() / ".env"
    if home_env.exists():
        return home_env

    # 默认返回 cwd 的 .env (即使不存在)
    return cwd_env


@lru_cache()
def get_settings() -> Config:
    """
    获取配置单例

    使用 lru_cache 保证单例模式，首次调用时加载配置。

    Returns:
        Config 配置单例
    """
    env_file = find_env_file()
    return Config(_env_file=env_file)


def reload_settings() -> Config:
    """
    重新加载配置（清除缓存）

    Returns:
        Config 新的配置单例
    """
    get_settings.cache_clear()
    return get_settings()


def apply_cli_args(cli_args: dict) -> Config:
    """
    应用命令行参数到配置

    Args:
        cli_args: argparse 解析的参数字典

    Returns:
        Config 更新后的配置
    """
    # 清除缓存并创建新配置
    get_settings.cache_clear()

    # 过滤 None 值
    filtered_args = {k: v for k, v in cli_args.items() if v is not None}

    env_file = find_env_file()
    return Config(_env_file=env_file, **filtered_args)


# 模块级单例变量
_settings: Config | None = None


def init_settings(cli_args: dict | None = None) -> Config:
    """
    初始化配置（在程序启动时调用）

    Args:
        cli_args: argparse 解析的参数字典（可选）

    Returns:
        Config 配置单例
    """
    global _settings

    get_settings.cache_clear()

    env_file = find_env_file()

    if cli_args:
        # 过滤 None 值
        filtered_args = {k: v for k, v in cli_args.items() if v is not None}
        _settings = Config(_env_file=env_file, **filtered_args)
    else:
        _settings = Config(_env_file=env_file)

    return _settings


def get_config() -> Config:
    """
    获取配置单例

    如果未初始化，返回默认配置。

    Returns:
        Config 配置单例
    """
    global _settings
    if _settings is None:
        return get_settings()
    return _settings


def set_config(config: Config):
    """
    设置配置

    Args:
        config: 新的配置对象
    """
    global _settings
    _settings = config


# 为了方便与其他模块兼容，提供字典访问接口
def get_config_dict() -> dict:
    """
    获取配置字典

    Returns:
        dict 配置字典
    """
    config = get_config()
    return config.model_dump()
