#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime
from pathlib import Path
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import parse_args, get_global_config, set_global_config
from tools.executor import ToolExecutor
from config import Config




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
        import json
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)


def run_trace_agent(config):
    """运行 TraceAgent 进行污点追踪审计"""
    from agents.trace_agent import TraceAgent
    from dataclasses import asdict
    import json

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
            print(f"[警告]Resume 模式未找到保存的配置，使用当前配置继续")
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
            print(f"[恢复模式] 配置已加载: {config.output_dir}/audit_config.json")

    agent = TraceAgent(
        project_path=config.project_path,
        debug=config.debug,
    )

    # audit_all 会自动保存 checkpoint 并在最后合并导出结果
    agent.audit_all(config.scan, output_dir=config.output_dir, resume=config.resume)


def main():
    """主函数"""
    import json

    # 1. 解析命令行参数
    config = parse_args()

    # 2. 打印配置信息
    if config.debug:
        print("\n[配置信息]")
        for key, value in dict(config).items():
            print(f"  {key}: {value}")
        print()
    run_trace_agent(config)
if __name__ == "__main__":
    main()
