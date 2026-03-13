#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CivetWeb URL 路由扫描脚本

扫描代码目录中的 mg_set_request_handler 调用，
提取 URL 注册信息和对应的回调函数。

用法:
    python scan.py <code_directory>

示例:
    python scan.py .
    python scan.py /app/src
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

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

# 项目类型和攻击面（硬编码）
PROJECT_TYPE = "c"
ATTACK_SURFACE = "civetweb"

# mg_set_request_handler 的正则表达式
# 匹配模式：mg_set_request_handler(ctx, "/path", callback_func, ...)
MG_SET_HANDLER_PATTERN = re.compile(
    r'mg_set_request_handler\s*\(\s*'
    r'[^,]+,\s*'           # 第一个参数：ctx
    r'["\']([^"\']+)["\']\s*,\s*'  # 第二个参数：URL 路径
    r'(\w+)\s*,\s*'        # 第三个参数：回调函数名
    r'[^)]*\)',            # 其余参数
    re.MULTILINE
)

# 更宽松的模式，匹配多行调用
MG_SET_HANDLER_PATTERN_MULTILINE = re.compile(
    r'mg_set_request_handler\s*\(\s*'
    r'[^,]+,\s*'
    r'["\']([^"\']+)["\']\s*,\s*'
    r'(\w+)\s*[,\)]',
    re.MULTILINE | re.DOTALL
)


def find_source_files(project_path: str) -> List[str]:
    """查找项目中所有 C/C++ 源文件"""
    files = []
    project = Path(project_path)

    for root, dirs, filenames in os.walk(project):
        # 跳过不需要的目录
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
    lines = content.split('\n')

    # 匹配函数定义：返回类型 函数名 (参数) { ... }
    pattern = re.compile(
        r'(?:static\s+)?(?:void|int|char\s*\*?|struct\s+\w+|\w+)\s*\*?\s*'
        rf'{re.escape(func_name)}\s*\([^)]*\)',
        re.MULTILINE
    )

    match = pattern.search(content)
    if not match:
        return ("", 0, 0)

    # 计算起始行号（从 1 开始）
    start_pos = match.start()
    start_line = content[:start_pos].count('\n') + 1

    # 找到函数体开始位置
    brace_start = content.find('{', match.end() - 1)
    if brace_start == -1:
        # 没有函数体，返回声明
        end = content.find(';', match.end())
        if end == -1:
            end = len(content)
        else:
            end += 1
        end_line = start_line + content[match.start():end].count('\n')
    else:
        # 计算匹配的闭合括号
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

    # 提取代码片段，带行号
    snippet_lines = content[start_pos:end].split('\n')
    code_with_lines = []
    for i, line in enumerate(snippet_lines):
        line_num = start_line + i
        code_with_lines.append(f"{line_num}: {line}")

    code_snippet = '\n'.join(code_with_lines)

    # 限制返回的代码长度（最多 20 行）
    if len(snippet_lines) > 20:
        code_snippet = '\n'.join(code_with_lines[:20]) + '\n    // ... (truncated)'
        end_line = start_line + 19

    return (code_snippet, start_line, end_line)


def find_code_snippet(content: str, func_name: str) -> tuple:
    """查找并返回函数定义的代码片段和行号

    Returns:
        tuple: (code_snippet, start_line, end_line)
    """
    return extract_function_definition(content, func_name)


def scan_file(filepath: Path, project_path: str) -> List[Dict]:
    """扫描单个文件，查找 mg_set_request_handler 调用"""
    results = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"警告：无法读取文件 {filepath}: {e}", file=sys.stderr)
        return results

    # 查找所有 mg_set_request_handler 调用
    matches = MG_SET_HANDLER_PATTERN_MULTILINE.finditer(content)

    for match in matches:
        url_path = match.group(1)
        callback_func = match.group(2)

        # 获取相对路径
        rel_path = str(filepath.relative_to(project_path))

        # 提取回调函数定义（带行号）
        code_snippet, start_line, end_line = find_code_snippet(content, callback_func)

        results.append({
            "url_path": url_path,
            "callback_func": callback_func,
            "file_path": rel_path,
            "start_line": start_line,
            "end_line": end_line,
            "code_snippet": code_snippet,
        })

    return results


def scan_directory(project_path: str) -> List[FunctionInfo]:
    """扫描整个目录，收集所有回调函数信息"""
    results = []
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
            func_info = FunctionInfo(
                func_name=r["callback_func"],
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                code_snippet=r["code_snippet"],
                project_type=PROJECT_TYPE,
                attack_surface=ATTACK_SURFACE,
            )
            results.append(func_info)
            print(f"  [{i}/{total}] 发现 URL 路由：{r['url_path']} -> {r['callback_func']}() @ lines {r['start_line']}-{r['end_line']}")

        # 显示进度
        if i % 10 == 0 or i == total:
            print(f"  进度：{i}/{total}", end="\r")

    print()
    return results


def output_results(results: List[FunctionInfo], output_format: str = "text"):
    """输出扫描结果"""
    if output_format == "json":
        import json
        print(json.dumps([r.model_dump() for r in results], indent=2))
    else:
        # 文本格式
        if not results:
            print("未找到 mg_set_request_handler 调用")
            return

        print(f"\n共找到 {len(results)} 个 URL 路由注册:\n")
        print("-" * 80)

        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.func_name}")
            print(f"    文件：{r.file_path}:{r.start_line}-{r.end_line}")
            print(f"    类型：{r.project_type}")
            print(f"    攻击面：{r.attack_surface}")
            if r.code_snippet:
                print(f"    代码片段:")
                for line in r.code_snippet.split('\n')[:10]:
                    print(f"        {line}")
            print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="扫描 CivetWeb URL 路由注册 (mg_set_request_handler)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scan.py .                           # 扫描当前目录
    python scan.py /app/src                    # 扫描指定目录
    python scan.py /app/src -f json            # JSON 格式输出
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

    # 验证路径
    if not os.path.isdir(args.code_directory):
        print(f"错误：目录不存在：{args.code_directory}", file=sys.stderr)
        sys.exit(1)

    # 扫描目录
    results = scan_directory(args.code_directory)

    # 输出结果
    output_results(results, args.format)


if __name__ == "__main__":
    main()