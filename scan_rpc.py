#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPC 消息处理函数注册扫描脚本

扫描代码目录中的 g_msg_handlers 注册，
提取 RPC 消息类型和对应的处理函数。

用法:
    python scan_rpc.py <code_directory>

示例:
    python scan_rpc.py .
    python scan_rpc.py /app/rpc_demo
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from models import FunctionInfo


# C/C++ 文件扩展名
C_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cxx", ".hxx", ".cc", ".hh"}

# 需要跳过的目录
SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "build", "out", "dist", "bin", "obj",
    "node_modules", "__pycache__", ".venv",
    "venv", "env", ".cache",
}

# 项目类型和攻击面
PROJECT_TYPE = "rpc"
ATTACK_SURFACE = "rpc_server"

# 外部输入点说明
INPUT_POINT = """# RPC 协议外部输入点说明

## 概述

RPC (Remote Procedure Call) 是 Web 服务器与业务处理进程之间的通信协议。
本文件描述了从外部请求到内部处理函数的数据流污染路径。

## 外部输入来源

通过 `read()` 等函数从 socket 接收到的原始 RPC 消息数据。

## RPC 消息结构

```c
typedef struct {
    uint32_t magic;       // 魔数: 0x52504300
    uint8_t version;      // 协议版本
    uint8_t flags;        // 标志位
    uint16_t msg_type;    // 消息类型 (LOGIN/DATA/HEARTBEAT)
    uint32_t msg_id;      // 消息ID/事务ID
    uint32_t payload_len; // 负载长度
} rpc_header_t;
```

## 消息处理函数类型

```c
typedef int (*msg_handler_t)(const uint8_t *request, size_t request_len,
                             uint8_t *response, size_t *response_len);
```

## 需要审计的函数模式

1. **消息接收函数**：`read`, `recv`
2. **消息解析函数**：`rpc_deserialize_*`
3. **业务处理函数**：`handle_login_msg`, `handle_data_msg`, `handle_heartbeat_msg`
4. **内存操作函数**：`memcpy`, `memmove`
"""

# 匹配 g_msg_handlers[RPC_MSG_*] = handle_*_msg;
MSG_HANDLER_PATTERN = re.compile(
    r'g_msg_handlers\s*\[\s*RPC_MSG_(\w+)\s*\]\s*=\s*(\w+)\s*;',
    re.MULTILINE
)

# 匹配函数定义：static int handle_*_msg(...) {
MSG_FUNC_DEF_PATTERN = re.compile(
    r'(?:static\s+)?(?:int|void)\s+(handle_\w+_msg)\s*\([^)]*\)\s*\{',
    re.MULTILINE
)


def find_source_files(project_path: str) -> List[str]:
    """查找项目中所有 C/C++ 源文件"""
    files = []
    project = Path(project_path)

    for root, dirs, filenames in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            filepath = Path(root) / filename
            if filepath.suffix.lower() in C_EXTENSIONS:
                relpath = filepath.relative_to(project)
                files.append(str(relpath))

    return sorted(files)


def extract_function_definition(content: str, func_name: str) -> tuple:
    """从文件内容中提取函数定义代码片段和行号

    Returns:
        tuple: (code_snippet, start_line, end_line)
    """
    # 匹配函数定义
    pattern = re.compile(
        r'(?:static\s+)?(?:int|void)\s+'
        rf'{re.escape(func_name)}\s*\([^)]*\)\s*',
        re.MULTILINE
    )

    match = pattern.search(content)
    if not match:
        return ("", 0, 0)

    start_pos = match.start()
    start_line = content[:start_pos].count('\n') + 1

    # 检查是否是声明（以分号结尾）
    end_pos = match.end()
    while end_pos < len(content) and content[end_pos] in ' \t\n':
        end_pos += 1

    if end_pos < len(content) and content[end_pos] == ';':
        end_line = start_line
        code_snippet = f"{start_line}: {match.group(0).strip()};"
        return (code_snippet, start_line, end_line)

    # 找到函数体
    brace_start = content.find('{', match.end() - 1)
    if brace_start == -1:
        end_line = start_line + content[match.start():].count('\n')
        code_snippet = f"{start_line}: {match.group(0).strip()}"
        return (code_snippet, start_line, end_line)

    brace_count = 1
    pos = brace_start + 1
    while pos < len(content) and brace_count > 0:
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1

    end = pos
    end_line = content[:end].count('\n') + 1

    snippet_lines = content[start_pos:end].split('\n')
    code_with_lines = []
    for i, line in enumerate(snippet_lines):
        code_with_lines.append(f"{start_line + i}: {line}")

    code_snippet = '\n'.join(code_with_lines)

    if len(snippet_lines) > 30:
        code_snippet = '\n'.join(code_with_lines[:30]) + '\n    // ... (truncated)'
        end_line = start_line + 29

    return (code_snippet, start_line, end_line)


def scan_file(filepath: Path, project_path: str) -> List[Dict]:
    """扫描单个文件，查找 g_msg_handlers 注册"""
    results = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"警告：无法读取文件 {filepath}: {e}", file=sys.stderr)
        return results

    rel_path = str(filepath.relative_to(project_path))

    # 先找到 g_msg_handlers 注册，获取函数名
    handler_funcs = []
    for match in MSG_HANDLER_PATTERN.finditer(content):
        msg_type = match.group(1)
        handler_func = match.group(2)
        handler_funcs.append({
            "msg_type": msg_type,
            "handler_func": handler_func,
        })

    # 在整个文件中查找这些函数的定义
    found_funcs = set()
    search_start = 0

    for func_info in handler_funcs:
        handler_func = func_info["handler_func"]

        # 每个函数只处理一次
        if handler_func in found_funcs:
            continue

        # 从上一次搜索位置之后继续查找
        match = MSG_FUNC_DEF_PATTERN.search(content, search_start)
        while match:
            found_func_name = match.group(1)
            if found_func_name == handler_func:
                found_funcs.add(handler_func)
                start_pos = match.start()
                start_line = content[:start_pos].count('\n') + 1

                # 计算函数体范围
                brace_start = content.find('{', start_pos)
                brace_count = 1
                pos = brace_start + 1
                while pos < len(content) and brace_count > 0:
                    if content[pos] == '{':
                        brace_count += 1
                    elif content[pos] == '}':
                        brace_count -= 1
                    pos += 1

                end_line = content[:pos].count('\n') + 1

                snippet_lines = content[start_pos:pos].split('\n')
                code_with_lines = []
                for i, line in enumerate(snippet_lines):
                    code_with_lines.append(f"{start_line + i}: {line}")

                code_snippet = '\n'.join(code_with_lines)

                if len(snippet_lines) > 50:
                    code_snippet = '\n'.join(code_with_lines[:50]) + '\n    // ... (truncated)'
                    end_line = start_line + 49

                results.append({
                    "msg_type": func_info["msg_type"],
                    "handler_func": handler_func,
                    "file_path": rel_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "code_snippet": code_snippet,
                })
                search_start = pos
                break
            else:
                # 继续查找下一个匹配
                search_start = match.end()
                match = MSG_FUNC_DEF_PATTERN.search(content, search_start)

    return results


def scan_directory(project_path: str) -> List[FunctionInfo]:
    """扫描整个目录，收集所有消息处理函数注册信息"""
    results = []
    seen_funcs = set()
    project = Path(project_path)

    files = find_source_files(project_path)
    total = len(files)

    print(f"扫描目录：{project_path}")
    print(f"找到 {total} 个 C/C++ 文件")
    print(f"Project Type: {PROJECT_TYPE}, Attack Surface: {ATTACK_SURFACE}")
    print()

    for i, file in enumerate(files, 1):
        filepath = project / file
        file_results = scan_file(filepath, project_path)

        for r in file_results:
            func_key = (r["handler_func"], r["file_path"])
            if func_key in seen_funcs:
                continue
            seen_funcs.add(func_key)

            func_info = FunctionInfo(
                func_name=r["handler_func"],
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                code_snippet=r["code_snippet"],
                input=INPUT_POINT,
            )
            results.append(func_info)

            print(f"  [{i}/{total}] 消息处理注册: RPC_MSG_{r['msg_type']} -> {r['handler_func']}() @ lines {r['start_line']}-{r['end_line']}")

        if i % 10 == 0 or i == total:
            print(f"  进度：{i}/{total}", end="\r")

    print()
    return results


def output_results(results: List[FunctionInfo], output_format: str = "text"):
    """输出扫描结果"""
    if output_format == "json":
        import json
        print(json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False))
    else:
        if not results:
            print("未找到 g_msg_handlers 注册")
            return

        print(f"\n共找到 {len(results)} 个 RPC 消息处理函数:\n")
        print("-" * 80)

        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.func_name}")
            print(f"    文件：{r.file_path}:{r.start_line}-{r.end_line}")
            if r.code_snippet:
                print(f"    代码片段:")
                for line in r.code_snippet.split('\n')[:15]:
                    print(f"        {line}")
            print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="扫描 RPC 消息处理函数注册 (g_msg_handlers)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scan_rpc.py .                           # 扫描当前目录
    python scan_rpc.py /app/rpc_demo               # 扫描指定目录
    python scan_rpc.py /app/rpc_demo -f json     # JSON 格式输出
        """,
    )

    parser.add_argument(
        "code_directory",
        type=str,
        help="代码目录路径",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.code_directory):
        print(f"错误：目录不存在：{args.code_directory}", file=sys.stderr)
        sys.exit(1)

    results = scan_directory(args.code_directory)
    output_results(results, args.format)


if __name__ == "__main__":
    main()
