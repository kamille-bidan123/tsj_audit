#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记事本项目扫描脚本
扫描项目中的 HTTP 接口处理函数，用于污点追踪审计
"""

import os
import re
from typing import List, Dict, Optional
from pathlib import Path


def find_c_files(project_path: str) -> List[str]:
    """查找项目中的 C 文件"""
    c_files = []
    project_path = Path(project_path)

    # 查找 src 目录下的所有 .c 文件
    src_dir = project_path / "src"
    if src_dir.exists():
        c_files.extend(str(f) for f in src_dir.glob("*.c"))

    # 查找根目录下的 .c 文件
    for f in project_path.glob("*.c"):
        c_files.append(str(f))

    return list(set(c_files))


def extract_functions_from_file(file_path: str) -> List[Dict]:
    """从 C 文件中提取函数定义"""
    functions = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"读取文件失败 {file_path}: {e}")
        return functions

    # 查找处理函数：handle_xxx 或 mg_set_request_handler
    # 1. handle_xxx 函数定义
    func_pattern = r'int\s+(handle_\w+)\s*\([^)]*\)\s*{'
    for match in re.finditer(func_pattern, content):
        func_name = match.group(1)
        start_line = content[:match.start()].count('\n') + 1

        # 查找函数结束位置
        brace_count = 0
        end_pos = match.end()
        for i, char in enumerate(content[match.start():]):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = match.start() + i + 1
                    break

        end_line = content[:end_pos].count('\n') + 1

        # 提取函数代码片段
        func_code = content[match.start():end_pos]

        functions.append({
            'func_name': func_name,
            'file_path': file_path,
            'start_line': start_line,
            'end_line': end_line,
            'code_snippet': func_code[:2000],  # 限制长度
            'input': 'HTTP 请求参数',  # 标识这是 HTTP 接口函数
            'handler_type': 'http'
        })

    # 2. mg_set_request_handler 注册的处理函数
    handler_pattern = r'mg_set_request_handler\s*\([^,]+,\s*"([^"]+)"\s*,\s*(\w+)\s*,'
    for match in re.finditer(handler_pattern, content):
        route = match.group(1)
        func_name = match.group(2)

        # 查找该函数的定义
        func_def = content.find(f'int {func_name}(')
        if func_def != -1:
            start_line = content[:func_def].count('\n') + 1

            # 简单估算结束行
            end_line = start_line + 50  # 假设每个处理函数约50行

            functions.append({
                'func_name': func_name,
                'file_path': file_path,
                'start_line': start_line,
                'end_line': end_line,
                'code_snippet': '',
                'input': f'HTTP {route} 路由',
                'handler_type': 'http',
                'route': route
            })

    return functions


def scan_directory(project_path: str) -> List[Dict]:
    """
    扫描项目目录，提取所有待审计的函数

    Args:
        project_path: 项目路径

    Returns:
        FunctionInfo 列表
    """
    all_functions = []

    # 获取 C 文件列表
    c_files = find_c_files(project_path)
    print(f"找到 {len(c_files)} 个 C 文件")

    for c_file in c_files:
        functions = extract_functions_from_file(c_file)
        all_functions.extend(functions)

    # 过滤重复的函数
    seen = set()
    unique_functions = []
    for func in all_functions:
        key = (func['func_name'], func['file_path'])
        if key not in seen:
            seen.add(key)
            unique_functions.append(func)

    # 添加一些特殊的入口点（已知的漏洞函数）
    # 这些函数在 main_web.c 中有实现
    known_vulnerable_functions = [
        {
            'func_name': 'handle_login',
            'file_path': 'src/main_web.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户名和密码',
            'handler_type': 'http',
            'route': '/login'
        },
        {
            'func_name': 'handle_register',
            'file_path': 'src/main_web.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户名、密码、邮箱',
            'handler_type': 'http',
            'route': '/register'
        },
        {
            'func_name': 'handle_reset_password',
            'file_path': 'src/main_web.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户ID、新密码',
            'handler_type': 'http',
            'route': '/reset_password'
        },
        {
            'func_name': 'handle_upload_notes',
            'file_path': 'src/main_web.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户ID、FTP主机',
            'handler_type': 'http',
            'route': '/ftp/upload'
        },
        {
            'func_name': 'handle_upload_logo',
            'file_path': 'src/main_web.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '文件名',
            'handler_type': 'http',
            'route': '/logo/upload'
        },
    ]

    # 添加数据库相关的入口点
    db_entry_points = [
        {
            'func_name': 'db_user_create',
            'file_path': 'src/db.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户输入（用户名、密码、邮箱）',
            'handler_type': 'db'
        },
        {
            'func_name': 'db_note_create',
            'file_path': 'src/db.c',
            'start_line': 1,
            'end_line': 100,
            'code_snippet': '',
            'input': '用户输入（标题、内容）',
            'handler_type': 'db'
        },
    ]

    all_functions = unique_functions + known_vulnerable_functions + db_entry_points

    # 移除重复
    seen = set()
    result = []
    for func in all_functions:
        key = (func['func_name'], func['file_path'])
        if key not in seen:
            seen.add(key)
            result.append(func)

    print(f"总共找到 {len(result)} 个接口函数")
    return result


# 兼容旧的 scan 函数名
scan = scan_directory

if __name__ == "__main__":
    # 如果作为脚本运行，扫描当前目录
    import sys
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    results = scan_directory(project_path)
    for func in results:
        print(f"  - {func['func_name']} @ {func['file_path']}:{func['start_line']}")
