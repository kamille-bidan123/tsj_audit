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
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径，相对于项目根目录",
                    },
                    "start": {
                        "type": "integer",
                        "description": "起始行号（可选）",
                    },
                    "end": {
                        "type": "integer",
                        "description": "结束行号（可选）",
                    },
                },
                "required": ["path"],
            },
        },
        "list_dir": {
            "description": "列出目录内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径（可选，默认为当前目录）",
                    },
                },
            },
        },
        "search_code": {
            "description": "在文件中搜索代码关键字",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式/关键字",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（可选，默认为当前目录）",
                    },
                },
                "required": ["pattern"],
            },
        },
    }

    def _get_config(self) -> dict:
        """获取全局配置"""
        return _get_global_config()

    def execute(self, command: str, args: dict) -> str:
        """执行命令，接收参数字典"""
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

    def _read_file(self, args: dict) -> str:
        path = args.get("path", "")
        start = args.get("start")
        end = args.get("end")

        if not path:
            return "错误：缺少 path 参数"

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
            selected_lines = lines[start_idx:end_idx]

            # 添加行号
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_idx+1):
                numbered_lines.append(f"{i}: {line}")

            content = "\n".join(numbered_lines)
        else:
            # 如果没有指定行范围，也为所有行添加行号
            lines = content.split("\n")
            numbered_lines = []
            for i, line in enumerate(lines, start=1):
                numbered_lines.append(f"{i}: {line}")

            content = "\n".join(numbered_lines)

        return content or "(文件为空)"

    def _list_dir(self, args: dict) -> str:
        path = args.get("path", ".")
        full_path = self._resolve_path(path)

        try:
            entries = os.listdir(full_path)
            if not entries:
                return "(目录为空)"
            return "\n".join(entries)
        except Exception as e:
            return f"错误：{e}"

    def _search_code(self, args: dict) -> str:
        """搜索代码关键字"""
        pattern = args.get("pattern", "")
        search_path = args.get("path", ".")

        if not pattern:
            return "错误：缺少 pattern 参数"

        # full_path = self._resolve_path(search_path)

        # 优先尝试 rg (ripgrep)
        try:
            # exclude tags文件
            result = subprocess.run(
                ["rg", "--glob", "!tags", "--ignore-case", "--color=never", "--line-number", pattern],
                capture_output=True,
                timeout=30,
                close_fds=True,
                cwd=self._get_config().get("project_path", ".")
            )
            # 手动解码，处理编码错误
            output = result.stdout.decode('utf-8', errors='replace').strip()
            if output:
                return output
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 回退到 grep
        try:
            result = subprocess.run(
                ["grep", "--exclude=tags", "-rni", "--color=never", pattern],
                capture_output=True,
                timeout=30,
                close_fds=True,
                cwd=self._get_config().get("project_path", ".")
            )
            output = result.stdout.decode('utf-8', errors='replace')
            if output:
                return output
        except subprocess.TimeoutExpired:
            return "错误：搜索超时"
        except Exception as e:
            return f"错误：{e}"

        return "(未找到匹配)"