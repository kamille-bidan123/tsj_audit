#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import parse_args, get_global_config, set_global_config
from tools.executor import ToolExecutor


def setup_docker(config):
    """根据配置设置 Docker 模式"""
    if config.enable_docker:
        container_id = config.docker_container
        if not container_id:
            print("错误：--enable-docker 需要指定 --docker-container")
            return False

        print(f"[初始化] Docker 模式已启用：container={container_id}, workdir={config.docker_workdir}")
    else:
        print("[初始化] 本地模式已启用")
    return True


def run_trace_agent(config):
    """运行 TraceAgent 进行污点追踪审计"""
    from agents.trace_agent import TraceAgent
    from dataclasses import asdict

    agent = TraceAgent(
        project_path=config.project_path,
        debug=config.debug,
    )

    # 检查是否启用断点续审
    resume = config.resume

    # 如果启用了断点续审，提示用户
    if resume and config.output_dir:
        print(f"[恢复模式] 将从输出目录加载中间信息继续审计: {config.output_dir}")

    # audit_all 会自动保存 checkpoint 并在最后合并导出结果
    agent.audit_all(config.scan, output_dir=config.output_dir, resume=resume)


def main():
    """主函数"""
    # 1. 解析命令行参数
    config = parse_args()


    # 3. 打印配置信息
    if config.debug:
        print("\n[配置信息]")
        for key, value in dict(config).items():
            print(f"  {key}: {value}")
        print()

    # 4. 设置 Docker 模式
    setup_docker(config)

    # 5. 运行 TraceAgent
    run_trace_agent(config)


if __name__ == "__main__":
    main()
