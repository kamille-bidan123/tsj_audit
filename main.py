#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码审计 Agent 工具 - 主入口

支持 trace_agent 模式进行污点追踪审计。

用法:
    # 基本使用
    python main.py --api-key sk-xxx --project-path /path/to/code

    # 指定项目类型和攻击面
    python main.py --api-key sk-xxx --project-type c --attack-surface civetweb

    # 调试模式
    python main.py --api-key sk-xxx --debug

    # 断点续审（从中间停止处恢复审计）
    python main.py --api-key sk-xxx --project-path /path/to/code --resume
"""

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
    resume = config.resume if hasattr(config, 'resume') else False

    # 如果启用了断点续审，提示用户
    if resume and config.output_dir:
        print(f"[恢复模式] 将从输出目录加载中间信息继续审计: {config.output_dir}")

    trace_results = agent.audit_all(config.scan, output_dir=config.output_dir, resume=resume)

    # 4. 导出结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"trace_results_{timestamp}.json"
    print(f"[4/4] 导出审计结果到：{config.output_dir}/{output_filename}")
    agent.export_results(results=trace_results, format="json", output_path=config.output_dir)
    agent.export_results(results=trace_results, format="html", output_path=config.output_dir)


    # 打印摘要
    total_entry_points = len(trace_results)
    total_code_contexts = sum(len(r.code_map) for r in trace_results)

    print(f"入口函数数：{total_entry_points}")
    print(f"代码上下文数：{total_code_contexts}")
    print(f"输出文件：{config.output_dir}/{output_filename}")


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
    print()

    # 5. 运行 TraceAgent
    run_trace_agent(config)


if __name__ == "__main__":
    main()
