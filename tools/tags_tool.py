#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代码符号导航工具

使用 ctags 和 cscope 进行代码符号查找。
配置从 cli 全局配置读取。
"""

import subprocess
import os
from typing import List
from tools.registry import ToolRegistry
import sys


def _get_global_config() -> dict:
    """从 cli 全局配置读取"""
    try:
        from cli import get_global_config
        return get_global_config()
    except ImportError:
        return {}


@ToolRegistry.register
class TagsTool:
    """代码符号导航工具

    使用 ctags 生成符号索引，使用 cscope 查找引用。
    支持 Go to Definition 和 Find References 功能。

    注意：使用前需要先运行 scripts/build_index.py 构建索引。
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
        "list_symbols": {
            "description": "列出索引中的符号",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "过滤模式（可选）",
                    },
                },
            },
        },
    }

    def _get_project_path(self) -> str:
        """获取项目路径"""
        return _get_global_config().get("project_path", ".")

    def execute(self, command: str, args: dict) -> str:
        """执行命令，接收参数字典"""
        if command == "go_to_def":
            return self._go_to_def(args)
        elif command == "find_refs":
            return self._find_refs(args)
        elif command == "list_symbols":
            return self._list_symbols(args)
        else:
            return f"错误：未知命令 '{command}'"


    def _check_index_exists(self) -> bool:
        """检查索引文件是否存在"""
        project_path = self._get_project_path()
        tags_file = os.path.join(project_path, "tags")
        cscope_file = os.path.join(project_path, "cscope.out")
        if _get_global_config().get("debug", True):
            print(f"[DEBUG] Checking index files: tags_file={tags_file}, cscope_file={cscope_file}", file=sys.stderr)
        return os.path.exists(tags_file) or os.path.exists(cscope_file)

    def _parse_tags(self, symbol: str) -> List[dict]:
        """解析 tags 文件查找符号定义"""
        project_path = self._get_project_path()
        tags_file = os.path.join(project_path, "tags")
        results = []

        if not os.path.exists(tags_file):
            return results

        try:
            with open(tags_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("!"):
                        continue

                    parts = line.split("\t")
                    if len(parts) >= 3:
                        tag_symbol = parts[0]
                        tag_file = parts[1]
                        tag_addr = parts[2]

                        # 精确匹配或前缀匹配
                        if tag_symbol == symbol or tag_symbol.startswith(symbol + "_"):
                            # 解析行号
                            line_num = 1
                            if "/;" in tag_addr:
                                addr_part = tag_addr.split("/;")[0]
                                try:
                                    # 尝试从地址提取行号
                                    if addr_part.startswith("/^") and addr_part.endswith("/"):
                                        # 搜索模式，需要从文件中查找
                                        pass
                                    elif addr_part.lstrip("?").isdigit():
                                        line_num = int(addr_part.lstrip("?"))
                                except (ValueError, IndexError):
                                    pass

                            # 尝试从标签信息中提取行号
                            if len(parts) > 3:
                                for part in parts[3:]:
                                    if part.startswith("line:"):
                                        line_num = int(part.split(":")[1])
                                        break

                            results.append({
                                "symbol": tag_symbol,
                                "file": tag_file,
                                "line": line_num,
                                "address": tag_addr,
                            })
        except Exception:
            pass

        return results

    def _search_cscope(self, symbol: str, query_type: int = 0) -> List[dict]:
        """搜索 cscope 数据库

        query_type:
            0: 查找所有（定义 + 引用）
            1: 查找定义 (global definition)
            2: 查找所有引用
            3: 查找函数调用
        """
        results = []
        cscope_dir = self._get_project_path()

        if not os.path.exists(os.path.join(cscope_dir, "cscope.out")):
            return results

        try:
            # cscope -d 只查询不构建，-L 输出格式
            cscope_cmd = [
                "cscope",
                "-d",  # 只查询
                "-L",  # 使用单行格式
                f"-{query_type}",  # 查询类型
                symbol,
            ]

            result = subprocess.run(
                cscope_cmd,
                capture_output=True,
                timeout=30,
                cwd=cscope_dir,
            )

            # 手动解码，处理编码错误
            stdout = result.stdout.decode('utf-8', errors='replace')
            if result.returncode == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    if not line:
                        continue

                    # cscope 输出格式：文件 函数 行号 内容
                    # 例如：test_code/example.c hello 4 void hello() {
                    parts = line.split(None, 3)
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
                            "content": parts[2] if len(parts) > 2 else "",
                        })
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            pass

        return results

    def _go_to_def(self, args: dict) -> str:
        """跳转到符号定义"""
        symbol = args.get("symbol", "")
        if not symbol:
            return "错误：缺少 symbol 参数"

        # 检查索引是否存在
        if not self._check_index_exists():
            return f"错误：索引不存在，请先运行 python scripts/build_index.py 构建索引"

        # 从 tags 查找定义
        definitions = self._parse_tags(symbol)

        if not definitions:
            # 尝试从 cscope 查找
            cscope_defs = self._search_cscope(symbol, query_type=0)
            for d in cscope_defs:
                definitions.append({
                    "symbol": symbol,
                    "file": d["file"],
                    "line": d["line"],
                    "address": "",
                })

        if not definitions:
            return f"未找到符号 '{symbol}' 的定义"

        # 返回第一个定义
        defs = definitions[:5]  # 最多返回 5 个
        output_lines = []
        for d in defs:
            file_path = d.get("file", "unknown")
            line_num = d.get("line", 1)
            output_lines.append(f"{file_path}:{line_num}")

        return "\n".join(output_lines)

    def _find_refs(self, args: dict) -> str:
        """查找符号的所有引用"""
        symbol = args.get("symbol", "")
        if not symbol:
            return "错误：缺少 symbol 参数"

        # 检查索引是否存在
        if not self._check_index_exists():
            return f"错误：索引不存在，请先运行 python scripts/build_index.py 构建索引"

        # 从 cscope 查找引用（使用 query 0 获取所有信息）
        all_results = self._search_cscope(symbol, query_type=0)

        if not all_results:
            return f"未找到符号 '{symbol}' 的引用"

        # 过滤出引用（排除定义行）
        refs = []
        for r in all_results:
            content = r.get("content", "")
            # 如果内容包含函数定义特征（以 { 结尾或包含函数声明），则是定义
            is_definition = (
                content.strip().endswith("{") or
                content.strip().endswith(";") or
                (f"{symbol}()" in content and "{" in content)
            )
            if not is_definition:
                refs.append(r)

        # 如果没有找到引用，返回定义信息
        if not refs:
            # 返回所有结果（包含定义）
            refs = all_results

        # 格式化输出
        output_lines = []
        for ref in refs[:20]:  # 最多返回 20 个
            file_path = ref.get("file", "unknown")
            line_num = ref.get("line", 0)
            content = ref.get("content", "").strip()
            output_lines.append(f"{file_path}:{line_num}: {content}")

        if len(refs) > 20:
            output_lines.append(f"... 还有 {len(refs) - 20} 个引用")

        if not output_lines:
            return "\n".join([f"{r['file']}:{r['line']}" for r in all_results[:5]])

        return "\n".join(output_lines)

    def _list_symbols(self, args: dict) -> str:
        """列出索引中的符号"""
        pattern = args.get("pattern")
        project_path = self._get_project_path()
        tags_file = os.path.join(project_path, "tags")

        if not os.path.exists(tags_file):
            return "错误：tags 文件不存在（请先运行 python scripts/build_index.py）"

        symbols = []
        try:
            with open(tags_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("!"):
                        continue

                    parts = line.split("\t")
                    if parts:
                        symbol = parts[0]
                        if pattern is None or pattern.lower() in symbol.lower():
                            symbols.append(symbol)
        except Exception as e:
            return f"错误：{e}"

        if not symbols:
            if pattern:
                return f"未找到匹配 '{pattern}' 的符号"
            return "索引为空"

        # 去重并排序
        symbols = sorted(set(symbols))

        # 限制输出数量
        if len(symbols) > 50:
            return "\n".join(symbols[:50]) + f"\n... 还有 {len(symbols) - 50} 个符号"

        return "\n".join(symbols)