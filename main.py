#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime
from pathlib import Path
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import parse_args
from config import Config
from models import FunctionInfo
from utils.terminal_status import get_terminal_status


def log(message: str) -> None:
    """Print user-facing progress logs immediately."""
    print(message, file=sys.stderr, flush=True)


def load_saved_config(output_dir: str) -> Config | None:
    """从输出目录加载之前保存的配置"""
    config_file = Path(output_dir) / "audit_config.json"
    if not config_file.exists():
        return None
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
        return Config(**config_dict)
    except Exception as e:
        print(f"[警告] 加载配置失败: {e}", file=sys.stderr)
        return None


def save_config(output_dir: str, config: Config):
    """保存配置到输出目录"""
    config_file = Path(output_dir) / "audit_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
    log(f"[配置] 已保存: {config_file}")


def discover_attack_surface_entries(config: Config) -> str:
    """Discover FunctionInfo entries from attack_surface_skill and save them as JSON."""
    from agents.entry_discovery_agent import EntryDiscoveryAgent

    if config.scan and config.attack_surface_skill:
        raise ValueError("--scan 和 --attack-surface-skill 不能同时使用，请二选一")
    if not config.attack_surface_skill:
        log(f"[入口] 使用 scan 输入: {config.scan}")
        return config.scan

    discovered_file = Path(config.output_dir or "output") / "discovered_functions.json"
    if config.resume and discovered_file.exists():
        log(f"[发现入口] resume 模式复用已发现入口: {discovered_file}")
        return str(discovered_file)

    log(
        f"[发现入口] 开始: skill={config.attack_surface_skill}, "
        f"runtime={config.agent_runtime}, project={config.project_path}"
    )
    get_terminal_status().set_stage("Entry Discovery", function_name="-", audit_type="-")
    agent = EntryDiscoveryAgent(
        attack_surface_skill=config.attack_surface_skill,
        project_path=config.project_path,
        debug=config.debug,
        output_dir=config.output_dir,
    )
    entries: list[FunctionInfo] = agent.discover()

    output_dir = Path(config.output_dir or "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(discovered_file, "w", encoding="utf-8") as f:
        json.dump([entry.model_dump() for entry in entries], f, indent=2, ensure_ascii=False)

    log(f"[发现入口] 使用 skill {config.attack_surface_skill} 发现 {len(entries)} 个入口函数")
    log(f"[发现入口] 已保存: {discovered_file}")
    return str(discovered_file)


def run_trace_agent(config):
    """运行 TraceAgent 进行污点追踪审计"""
    from agents.trace_agent import TraceAgent

    log(
        f"[启动] runtime={config.agent_runtime}, project={config.project_path}, "
        f"output={config.output_dir}, scan={config.scan or '-'}, "
        f"attack_surface_skill={config.attack_surface_skill or '-'}"
    )
    status = get_terminal_status()
    status.start()
    status.set_runtime(config.agent_runtime)
    status.set_stage("启动", function_name="-", audit_type="-")

    # 检查输出目录是否有现有检查点
    has_checkpoints = False
    if config.output_dir:
        checkpoint_dir = Path(config.output_dir) / "checkpoints"
        if checkpoint_dir.exists():
            checkpoint_files = list(checkpoint_dir.glob("*.json"))
            has_checkpoints = len(checkpoint_files) > 0

    # 如果是 resume 模式
    if config.resume:
        if not config.output_dir:
            print("错误：--resume 模式需要指定 --output-dir")
            sys.exit(1)

        # 保存命令行指定的 resume 参数
        resume_flag = config.resume

        # 加载保存的配置
        saved_config = load_saved_config(config.output_dir)
        if saved_config:
            print(f"[恢复模式] 使用已保存的配置: {config.output_dir}")
            # 使用保存的配置，忽略 resume 字段（由命令行决定）
            config = saved_config
            config.resume = resume_flag
        else:
            log(f"[警告]Resume 模式未找到保存的配置，使用当前配置继续")
    else:
        # 非 resume 模式，检查是否有现有检查点
        if has_checkpoints:
            print("\n[错误] 已有审计记录，使用这个目录会覆盖之前的记录")
            print("请选择：")
            print("  1. 使用新的输出目录：--output-dir ./new_output")
            print("  2. 或使用 resume 模式恢复：--resume")
            print()
            print("提示：审计数据保存在 output/checkpoints/ 目录")
            sys.exit(1)

    # 保存当前配置到输出目录
    if config.output_dir:
        save_config(config.output_dir, config)
        if config.resume:
            log(f"[恢复模式] 配置已加载: {config.output_dir}/audit_config.json")

    try:
        scan_path = discover_attack_surface_entries(config)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    agent = TraceAgent(
        project_path=config.project_path,
        debug=config.debug,
        on_functions_loaded=lambda funcs: status.set_functions(funcs),
        on_function_start=lambda func: status.start_function(func.func_name, func.file_path),
        on_function_complete=lambda func: status.complete_function(func.func_name),
        on_function_restored=lambda func: status.restore_function(func.func_name, func.file_path),
    )

    # audit_all 会自动保存 checkpoint 并在最后合并导出结果
    agent.audit_all(scan_path, output_dir=config.output_dir, resume=config.resume)
    status.set_stage("完成", function_name="-", audit_type="-")
    log("[完成] 审计流程结束")


def main():
    """主函数"""
    # 1. 解析命令行参数
    config = parse_args()

    # 2. 打印配置信息
    if config.debug:
        print("\n[配置信息]")
        for key, value in dict(config).items():
            print(f"  {key}: {value}")
        print()

    status = get_terminal_status()

    def run() -> None:
        try:
            run_trace_agent(config)
        finally:
            status.stop()

    try:
        status.run_with(run)
    finally:
        status.stop()


if __name__ == "__main__":
    main()
