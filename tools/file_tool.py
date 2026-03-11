#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件操作工具

提供文件读取、目录列表和代码搜索功能。
配置从 cli 全局配置读取。
"""

import re
import os
import shlex
import subprocess
from tools.registry import ToolRegistry


def _get_global_config() -> dict:
    """从 cli 全局配置读取"""
    try:
        from cli import get_global_config
        return get_global_config()
    except ImportError:
        return {}


@ToolRegistry.register
class FileTool:
    """文件操作相关工具"""

    name = "file_tool"
    description = "文件读写和目录操作"

    commands = {
        "read_file": {
            "description": "读取文件内容，支持指定行范围",
            "usage": "read_file <path>[:<start>-<end>]",
            "examples": [
                "read_file main.py",
                "read_file open.c:1-20",
                "read_file config.json:10-50",
            ],
        },
        "list_dir": {
            "description": "列出目录内容",
            "usage": "list_dir [path]",
            "examples": ["list_dir .", "list_dir /src", "list_dir"],
        },
        "search_code": {
            "description": "在文件中搜索代码关键字",
            "usage": "search_code <pattern> [path]",
            "examples": [
                "search_code \"def login\" .",
                "search_code \"TODO\" src/",
                "search_code \"vulnerability\"",
            ],
        },
    }

    def _get_config(self) -> dict:
        """获取全局配置"""
        return _get_global_config()

    def execute(self, command: str, args: str) -> str:
        if command == "read_file":
            return self._read_file(args)
        elif command == "list_dir":
            return self._list_dir(args)
        elif command == "search_code":
            return self._search_code(args)
        else:
            return f"错误：未知命令 '{command}'"

    def _resolve_path(self, path: str) -> str:
        """解析路径，相对于项目路径"""
        if path.startswith("/"):
            return path
        project_path = self._get_config().get("project_path", ".")
        return os.path.join(project_path, path)

    def _read_file(self, args: str) -> str:
        # 解析 path:line_start-line_end
        match = re.match(r"^(.+?)(?::(\d+)-(\d+))?$", args.strip())
        if not match:
            return f"错误：无效的参数格式 '{args}'"

        path = match.group(1)
        start = int(match.group(2)) if match.group(2) else None
        end = int(match.group(3)) if match.group(3) else None

        full_path = self._resolve_path(path)

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在 '{path}'"
        except Exception as e:
            return f"错误：{e}"

        # 处理行范围
        if start is not None or end is not None:
            lines = content.split("\n")
            start_idx = (start - 1) if start else 0
            end_idx = end if end else len(lines)
            lines = lines[start_idx:end_idx]
            content = "\n".join(lines)

        return content or "(文件为空)"

    def _list_dir(self, args: str) -> str:
        path = args.strip() if args.strip() else "."
        full_path = self._resolve_path(path)

        try:
            entries = os.listdir(full_path)
            if not entries:
                return "(目录为空)"
            return "\n".join(entries)
        except Exception as e:
            return f"错误：{e}"

    def _search_code(self, args: str) -> str:
        """搜索代码关键字"""
        try:
            parts = shlex.split(args)
        except ValueError:
            parts = args.split()

        if not parts:
            return "错误：用法 search_code <pattern> [path]"

        pattern = parts[0]
        search_path = parts[1] if len(parts) > 1 else "."
        full_path = self._resolve_path(search_path)

        # 优先尝试 rg (ripgrep)
        try:
            result = subprocess.run(
                ["rg", "--ignore-case", "--color=never", pattern, full_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 回退到 grep
        try:
            result = subprocess.run(
                ["grep", "-ri", "--color=never", pattern, full_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return "错误：搜索超时"
        except Exception as e:
            return f"错误：{e}"

        return "(未找到匹配)"
