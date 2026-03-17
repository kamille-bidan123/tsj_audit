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

    print("=" * 60)
    print("TraceAgent 代码污点追踪审计")
    print("=" * 60)
    print()

    # 3. 审计所有接口函数（两阶段）
    print(" 开始审计分析...")
    print()

    trace_results = agent.audit_all(config.scan)
    print()

    # 4. 导出结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"trace_results_{timestamp}.json"
    print(f"[4/4] 导出审计结果到：{config.output_dir}/{output_filename}")
    agent.export_results(trace_results, output_filename, format="json", output_dir=config.output_dir)

    print()
    print("=" * 60)
    print("审计完成!")
    print("=" * 60)

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
        for key, value in asdict(config).items():
            print(f"  {key}: {value}")
        print()

    # 4. 设置 Docker 模式
    setup_docker(config)
    print()

    # 5. 运行 TraceAgent
    run_trace_agent(config)


if __name__ == "__main__":
    main()
