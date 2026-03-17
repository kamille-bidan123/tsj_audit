#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPC 数据流分析脚本

用于分析 C 语言 RPC 项目中的数据流：
1. 找到所有序列化/反序列化函数
2. 跟踪网络收发函数
3. 追踪消息处理分发
"""

import subprocess
import os
import re
from typing import List, Dict


def run_cquery(query: str, project_path: str) -> List[str]:
    """运行 cquery 查询"""
    try:
        result = subprocess.run(
            ["cquery", "--output=lines", query],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=30
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except Exception as e:
        print(f"cquery error: {e}")
        return []


def find_serialization_functions(project_path: str) -> List[Dict]:
    """查找序列化函数"""
    functions = []
    patterns = [
        r"(serialize|serialize_|to_bytes|pack_|encode)",
        r"(deserialize|deserialize_|from_bytes|unpack_|decode)",
    ]

    for pattern in patterns:
        try:
            result = subprocess.run(
                ["rg", "--no-header", "-n", pattern, project_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        functions.append({
                            "name": re.search(r"(serialize|deserialize|pack_|unpack_|encode|decode)[_a-zA-Z0-9]*", parts[2]),
                            "file": parts[0],
                            "line": parts[1],
                            "content": parts[2].strip()
                        })
        except Exception as e:
            pass

    return functions


def find_network_functions(project_path: str) -> List[Dict]:
    """查找网络通信函数"""
    functions = []
    patterns = [
        r"(send|recv|socket|bind|listen|accept|write|read)",
        r"(htonl|htons|ntohl|ntohs|htonll|ntohll)",
    ]

    for pattern in patterns:
        try:
            result = subprocess.run(
                ["rg", "--no-header", "-n", pattern, project_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        func_name = re.search(r"(\w+(?:send|recv|socket|htonl|ntohl)?)\s*\(", parts[2])
                        if func_name:
                            functions.append({
                                "name": func_name.group(1),
                                "file": parts[0],
                                "line": parts[1],
                                "content": parts[2].strip()
                            })
        except Exception as e:
            pass

    return functions


def find_message_dispatch(project_path: str) -> List[Dict]:
    """查找消息分发逻辑"""
    dispatches = []

    # 查找 switch-case 消息类型分发
    try:
        result = subprocess.run(
            ["rg", "--no-header", "-n", r"switch\s*\(.*msg.*type|case\s+RPC_MSG_", project_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    dispatches.append({
                        "type": "switch",
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2].strip()
                    })
    except Exception as e:
        pass

    # 查找函数指针表分发
    try:
        result = subprocess.run(
            ["rg", "--no-header", "-n", r"handler\[|dispatch_table|msg_handler", project_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    dispatches.append({
                        "type": "function_ptr",
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2].strip()
                    })
    except Exception as e:
        pass

    return dispatches


def analyze_rpc_flow(project_path: str) -> str:
    """分析 RPC 数据流"""
    print("=" * 60)
    print("RPC 数据流分析报告")
    print("=" * 60)

    print("\n【1】序列化/反序列化函数")
    print("-" * 40)
    funcs = find_serialization_functions(project_path)
    for f in funcs[:10]:  # 只显示前10个
        print(f"  {f['file']}:{f['line']}")
        print(f"    {f['content']}")

    print("\n【2】网络通信函数")
    print("-" * 40)
    funcs = find_network_functions(project_path)
    for f in funcs[:10]:
        print(f"  {f['file']}:{f['line']}")
        print(f"    {f['content']}")

    print("\n【3】消息分发逻辑")
    print("-" * 40)
    dispatches = find_message_dispatch(project_path)
    for d in dispatches:
        print(f"  {d['file']}:{d['line']}")
        print(f"    [{d['type']}] {d['content']}")

    print("\n" + "=" * 60)
    print("分析完成")
    print("=" * 60)

    return "分析完成"


if __name__ == "__main__":
    import sys
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    analyze_rpc_flow(project_path)
