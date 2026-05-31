#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ioctl 接口扫描脚本。

扫描代码目录中的 ioctl 注册和处理函数，输出轻量 EntrySpec。

用法:
    python scan.py <code_directory>
    python scan.py <code_directory> -f json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


def _add_repo_root_to_path() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "models.py").exists():
            sys.path.insert(0, str(parent))
            return


_add_repo_root_to_path()

from models import EntrySpec  # noqa: E402


C_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cxx", ".hxx", ".cc", ".hh"}
SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "build",
    "out",
    "dist",
    "bin",
    "obj",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".cache",
}

IOCTL_SKILL = "ioctl_audit"

IOCTL_REGISTRATION_PATTERNS = [
    re.compile(r"\.(?:unlocked_ioctl|compat_ioctl|ioctl|proc_ioctl)\s*=\s*([A-Za-z_]\w*)"),
]

FUNCTION_HEADER_PATTERN = re.compile(
    r"""
    (?P<header>
        (?:static\s+)?
        (?:asmlinkage\s+)?
        (?:long|int|unsigned\s+long|unsigned\s+int|ssize_t|\w+_t|\w+)
        \s+\*?\s*
        (?P<name>[A-Za-z_]\w*)
        \s*\(
            (?P<params>[^;{}]*?)
        \)
    )
    \s*\{
    """,
    re.MULTILINE | re.DOTALL | re.VERBOSE,
)

IOCTL_NAME_FRAGMENT = re.compile(r"ioctl", re.IGNORECASE)


def find_source_files(project_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        root_path = Path(root)
        for filename in filenames:
            filepath = root_path / filename
            if filepath.suffix.lower() in C_EXTENSIONS:
                files.append(filepath)
    return sorted(files)


def _line_number(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


def _looks_like_ioctl_handler(name: str, params: str) -> bool:
    normalized = re.sub(r"\s+", " ", params)
    has_ioctl_name = bool(IOCTL_NAME_FRAGMENT.search(name))
    has_cmd_arg = "cmd" in normalized and "arg" in normalized
    has_common_types = "struct file" in normalized or "inode" in normalized
    return has_ioctl_name or (has_cmd_arg and has_common_types)


def _function_definitions(content: str) -> Iterable[tuple[str, int, str]]:
    for match in FUNCTION_HEADER_PATTERN.finditer(content):
        name = match.group("name")
        params = match.group("params")
        if _looks_like_ioctl_handler(name, params):
            yield name, _line_number(content, match.start()), params


def _registered_ioctl_names(content: str) -> set[str]:
    names: set[str] = set()
    for pattern in IOCTL_REGISTRATION_PATTERNS:
        names.update(match.group(1) for match in pattern.finditer(content))
    return names


def scan_file(filepath: Path, project_path: Path) -> list[EntrySpec]:
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(f"警告：无法读取文件 {filepath}: {exc}", file=sys.stderr)
        return []

    rel_path = str(filepath.relative_to(project_path))
    registered_names = _registered_ioctl_names(content)
    entries: list[EntrySpec] = []

    for func_name, start_line, _params in _function_definitions(content):
        if func_name in registered_names or IOCTL_NAME_FRAGMENT.search(func_name):
            entries.append(
                EntrySpec(
                    func_name=func_name,
                    file_path=rel_path,
                    start_line=start_line,
                    skill=IOCTL_SKILL,
                )
            )

    return entries


def scan_directory(project_path: Path) -> list[EntrySpec]:
    files = find_source_files(project_path)
    results: list[EntrySpec] = []
    seen: set[tuple[str, str, int | None]] = set()

    print(f"扫描目录：{project_path}")
    print(f"找到 {len(files)} 个 C/C++ 文件")
    print(f"Attack Surface Skill: {IOCTL_SKILL}")
    print()

    for index, filepath in enumerate(files, 1):
        for entry in scan_file(filepath, project_path):
            key = (entry.func_name, entry.file_path, entry.start_line)
            if key in seen:
                continue
            seen.add(key)
            results.append(entry)
            print(
                f"  [{index}/{len(files)}] 发现 ioctl handler: "
                f"{entry.func_name} @ {entry.file_path}:{entry.start_line}"
            )

        if index % 10 == 0 or index == len(files):
            print(f"  进度：{index}/{len(files)}", end="\r")

    print()
    return results


def output_results(results: list[EntrySpec], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False))
        return

    if not results:
        print("未找到 ioctl handler")
        return

    print(f"\n共找到 {len(results)} 个 ioctl handler:\n")
    print("-" * 80)
    for index, entry in enumerate(results, 1):
        print(f"[{index}] {entry.func_name}")
        print(f"    文件：{entry.file_path}:{entry.start_line}")
        print(f"    skill：{entry.skill}")
        print("-" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="扫描 ioctl handler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("code_directory", type=str, help="代码目录路径")
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式",
    )
    args = parser.parse_args()

    project_path = Path(args.code_directory).resolve()
    if not project_path.is_dir():
        print(f"错误：目录不存在：{project_path}", file=sys.stderr)
        sys.exit(1)

    output_results(scan_directory(project_path), args.format)


if __name__ == "__main__":
    main()
