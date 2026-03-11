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
        project_type=config.project_type,
        attack_surface=config.attack_surface,
        project_path=config.project_path,
        debug=config.debug,
    )

    print("=" * 60)
    print("TraceAgent 代码污点追踪审计")
    print("=" * 60)
    print()

    # 1. 加载扫描结果
    print(f"[1/4] 扫描代码目录：{config.project_path}")
    scan_results = agent.load_scan_results()
    print(f"      找到 {len(scan_results)} 个接口函数")

    for func in scan_results:
        print(f"        - {func.func_name} @ {func.file_path}:{func.func_name}")
    print()

    # 2. 加载输入知识
    print("[2/4] 加载输入知识...")
    input_knowledge = agent.load_input_knowledge()
    if input_knowledge:
        print(f"      已加载 {len(input_knowledge)} 字节")
    else:
        print("      [警告] 未找到输入知识文件")
    print()

    # 3. 审计所有接口函数（两阶段）
    print("[3/4] 开始审计分析...")
    print("      阶段 1: 多轮对话探索 (file_tool + tags_tool)")
    print("      阶段 2: 生成 codemap")
    print()
    trace_results = agent.audit_all(max_turns=10)
    print()

    # 4. 导出结果
    output_path = "trace_results.json"
    print(f"[4/4] 导出审计结果到：{output_path}")
    agent.export_results(trace_results, output_path, format="json")

    # 同时导出文本格式
    output_txt = "trace_results.txt"
    agent.export_results(trace_results, output_txt, format="text")
    print(f"      文本格式：{output_txt}")

    print()
    print("=" * 60)
    print("审计完成!")
    print("=" * 60)

    # 打印摘要
    total_entry_points = len(trace_results)
    total_code_contexts = sum(len(r.code_map) for r in trace_results)
    total_tool_calls = sum(len(r.exploration.tool_calls) for r in trace_results)

    print(f"入口函数数：{total_entry_points}")
    print(f"代码上下文数：{total_code_contexts}")
    print(f"工具调用次数：{total_tool_calls}")
    print(f"输出文件：{output_path}, {output_txt}")


def main():
    """主函数"""
    # 1. 解析命令行参数
    config = parse_args()


    # 3. 打印配置信息
    if config.debug:
        print("=" * 60)
        print("配置信息")
        print("=" * 60)
        print(f"API URL: {config.base_url}")
        print(f"模型：{config.model_name}")
        print(f"项目路径：{config.project_path}")
        print(f"项目类型：{config.project_type}")
        print(f"攻击面：{config.attack_surface}")
        print(f"调试模式：{config.debug}")
        print()

    # 4. 设置 Docker 模式
    setup_docker(config)
    print()

    # 5. 运行 TraceAgent
    run_trace_agent(config)


if __name__ == "__main__":
    main()
