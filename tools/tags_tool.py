#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ctags/cscope-backed symbol navigation helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List

from config import get_config


class TagsTool:
    """代码符号导航工具。

    使用前需要先运行 `scripts/build_index.py` 构建 tags/cscope 索引。
    """

    name = "tags_tool"
    description = "代码符号导航（go_to_def, find_refs）"

    commands = {
        "go_to_def": {
            "description": "跳转到符号定义处",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "要查找定义的符号名",
                    },
                },
                "required": ["symbol"],
            },
        },
        "find_refs": {
            "description": "查找符号的所有引用",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "要查找引用的符号名",
                    },
                },
                "required": ["symbol"],
            },
        },
    }

    def _get_project_path(self) -> str:
        return get_config().project_path

    def execute(self, command: str, args: dict) -> str:
        if command == "go_to_def":
            return self._go_to_def(args)
        if command == "find_refs":
            return self._find_refs(args)
        return f"错误：未知命令 '{command}'"

    def _check_index_exists(self) -> bool:
        project_path = self._get_project_path()
        tags_file = os.path.join(project_path, "tags")
        cscope_file = os.path.join(project_path, "cscope.out")
        if get_config().debug:
            print(f"[DEBUG] Checking index files: tags_file={tags_file}, cscope_file={cscope_file}", file=sys.stderr)
        return os.path.exists(tags_file) or os.path.exists(cscope_file)

    def _parse_tags(self, symbol: str) -> List[dict]:
        project_path = self._get_project_path()
        tags_file = os.path.join(project_path, "tags")
        results = []

        if not os.path.exists(tags_file):
            return results

        try:
            with open(tags_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("!"):
                        continue

                    parts = line.split("\t")
                    if len(parts) < 3:
                        continue

                    tag_symbol = parts[0]
                    tag_file = parts[1]
                    tag_addr = parts[2]

                    if tag_symbol != symbol and not tag_symbol.startswith(symbol + "_"):
                        continue

                    line_num = 1
                    if "/;" in tag_addr:
                        addr_part = tag_addr.split("/;")[0]
                        try:
                            if addr_part.lstrip("?").isdigit():
                                line_num = int(addr_part.lstrip("?"))
                        except (ValueError, IndexError):
                            pass

                    for part in parts[3:]:
                        if part.startswith("line:"):
                            try:
                                line_num = int(part.split(":", 1)[1])
                            except ValueError:
                                pass
                            break

                    results.append({
                        "symbol": tag_symbol,
                        "file": tag_file,
                        "line": line_num,
                        "address": tag_addr,
                    })
        except OSError:
            pass

        return results

    def _search_cscope(self, symbol: str, query_type: int = 0) -> List[dict]:
        results = []
        cscope_dir = self._get_project_path()

        if not os.path.exists(os.path.join(cscope_dir, "cscope.out")):
            return results

        try:
            result = subprocess.run(
                ["cscope", "-d", "-L", f"-{query_type}", symbol],
                capture_output=True,
                timeout=30,
                cwd=cscope_dir,
                check=False,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            if result.returncode != 0 or not stdout:
                return results

            for line in stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(None, 3)
                try:
                    if len(parts) >= 4:
                        results.append({
                            "file": parts[0],
                            "function": parts[1],
                            "line": int(parts[2]),
                            "content": parts[3],
                        })
                    elif len(parts) >= 3:
                        results.append({
                            "file": parts[0],
                            "function": "",
                            "line": int(parts[1]),
                            "content": parts[2],
                        })
                except ValueError:
                    continue
        except (subprocess.TimeoutExpired, OSError):
            pass

        return results

    def _go_to_def(self, args: dict) -> str:
        symbol = args.get("symbol", "")
        if not symbol:
            return "错误：缺少 symbol 参数"

        if not self._check_index_exists():
            return "错误：索引不存在，请先运行 python scripts/build_index.py 构建索引"

        definitions = self._parse_tags(symbol)
        if not definitions:
            for item in self._search_cscope(symbol, query_type=1):
                definitions.append({
                    "symbol": symbol,
                    "file": item["file"],
                    "line": item["line"],
                    "address": "",
                })

        if not definitions:
            return f"未找到符号 '{symbol}' 的定义"

        return "\n".join(
            f"{item.get('file', 'unknown')}:{item.get('line', 1)}"
            for item in definitions[:5]
        )

    def _find_refs(self, args: dict) -> str:
        symbol = args.get("symbol", "")
        if not symbol:
            return "错误：缺少 symbol 参数"

        if not self._check_index_exists():
            return "错误：索引不存在，请先运行 python scripts/build_index.py 构建索引"

        all_results = self._search_cscope(symbol, query_type=2)
        if not all_results:
            return f"未找到符号 '{symbol}' 的引用"

        refs = []
        for item in all_results:
            content = item.get("content", "")
            is_definition = (
                content.strip().endswith("{")
                or content.strip().endswith(";")
                or (f"{symbol}()" in content and "{" in content)
            )
            if not is_definition:
                refs.append(item)

        if not refs:
            refs = all_results

        output_lines = []
        for ref in refs[:100]:
            file_path = ref.get("file", "unknown")
            line_num = ref.get("line", 0)
            content = ref.get("content", "").strip()
            output_lines.append(f"{file_path}:{line_num}: {content}")

        if len(refs) > 100:
            output_lines.append(f"... 还有 {len(refs) - 100} 个引用")

        return "\n".join(output_lines)


def go_to_def(symbol: str) -> str:
    """Find definitions for a symbol using ctags/cscope indexes."""
    return TagsTool().execute("go_to_def", {"symbol": symbol})


def find_refs(symbol: str) -> str:
    """Find references for a symbol using ctags/cscope indexes."""
    return TagsTool().execute("find_refs", {"symbol": symbol})
