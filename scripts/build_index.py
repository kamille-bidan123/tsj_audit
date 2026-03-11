#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C/C++ 代码索引构建脚本

使用 ctags 和 cscope 的增量更新机制构建代码索引。
支持进度显示，适合大型项目。

用法:
    python build_index.py <project_path>

示例:
    python build_index.py .
    python build_index.py /app/src
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Set


# C/C++ 文件扩展名
C_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cxx", ".hxx", ".cc", ".hh"}

# 需要跳过的目录
SKIP_DIRS = {
    ".git", ".svn", ".hg",  # 版本控制
    "build", "out", "dist", "bin", "obj",  # 构建目录
    "node_modules", "__pycache__", ".venv",  # 依赖目录
    "venv", "env", ".cache",  # 虚拟环境
}


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


def build_ctags(project_path: str, files: List[str], verbose: bool = False) -> bool:
    """
    构建 ctags 索引

    ctags 不支持增量更新，直接全量生成
    """
    tags_file = os.path.join(project_path, "tags")
    filelist_path = os.path.join(project_path, ".ctags-files")

    # 写入文件列表（使用绝对路径）
    abs_files = [os.path.join(project_path, f) for f in files]
    with open(filelist_path, "w") as f:
        f.write("\n".join(abs_files))

    # 使用 -L 选项时，需要用空格而不是等号
    cmd = [
        "ctags",
        "--languages=C,C++",
        "--c-kinds=+p",
        "--fields=+n",
        "-f", tags_file,
        "-L", filelist_path,
    ]

    if verbose:
        print(f"执行：{' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0 and not os.path.exists(tags_file):
        print(f"ctags 失败：{result.stderr}", file=sys.stderr)
        return False

    return True


def build_cscope_incremental(project_path: str, files: List[str], verbose: bool = False) -> bool:
    """
    增量构建 cscope 索引

    cscope 支持增量更新：
    1. 使用 -i 指定文件列表
    2. 使用 -u 只更新变化的文件
    """
    cscope_filelist = os.path.join(project_path, ".cscope-files")
    cscope_out = os.path.join(project_path, "cscope.out")

    # 写入文件列表（cscope 格式）
    with open(cscope_filelist, "w") as f:
        for filepath in files:
            f.write(f"{filepath}\n")

    # 检查是否存在旧数据库
    has_existing = os.path.exists(cscope_out)

    if has_existing:
        # 增量更新模式
        print("检测到现有数据库，使用增量更新模式...")

        # 使用 cscope -u 增量更新
        cmd = [
            "cscope",
            "-b",  # 只构建
            "-q",  # 构建快速查找
            "-u",  # 增量更新
            "-f", cscope_out,
            "-i", cscope_filelist,
        ]
    else:
        # 全量构建模式
        cmd = [
            "cscope",
            "-b",  # 只构建
            "-q",  # 构建快速查找
            "-R",  # 递归
            "-f", cscope_out,
            "-i", cscope_filelist,
        ]

    if verbose:
        print(f"执行：{' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            # 检查是否是 warning（ctags 常见问题）
            if "error" in result.stderr.lower() and not os.path.exists(cscope_out):
                print(f"cscope 失败：{result.stderr}", file=sys.stderr)
                return False
    except subprocess.TimeoutExpired:
        print("cscope 构建超时", file=sys.stderr)
        return False

    return os.path.exists(cscope_out)


def build_index_with_progress(
    project_path: str,
    verbose: bool = False,
    show_progress: bool = True
) -> bool:
    """
    构建索引并显示进度

    ctags 分批处理显示进度，cscope 一次性构建（速度较快）
    """
    print(f"扫描项目：{project_path}")

    # 1. 查找所有源文件
    files = find_source_files(project_path)
    total = len(files)

    if total == 0:
        print("错误：未找到 C/C++ 源文件", file=sys.stderr)
        return False

    print(f"找到 {total} 个 C/C++ 文件")

    # 2. 构建 ctags（分批显示进度）
    if show_progress:
        print("\n[1/2] 构建 ctags 索引...")
    else:
        print("构建 ctags 索引...")

    tags_file = os.path.join(project_path, "tags")
    filelist_path = os.path.join(project_path, ".ctags-files")

    # 写入完整文件列表
    abs_files = [os.path.join(project_path, f) for f in files]
    with open(filelist_path, "w") as f:
        f.write("\n".join(abs_files))

    if show_progress and total > 100:
        # 分批 ctags，模拟进度
        batch_size = max(50, total // 20)
        with open(tags_file, "w") as tf:
            tf.write("")  # 清空

        for i in range(0, total, batch_size):
            batch = abs_files[i:i + batch_size]
            batch_filelist = os.path.join(project_path, ".ctags-batch")

            with open(batch_filelist, "w") as f:
                f.write("\n".join(batch))

            cmd = [
                "ctags",
                "--languages=C,C++",
                "--c-kinds=+p",
                "--fields=+n",
                "-f", tags_file,
                "-L", batch_filelist,
                "-a",  # 追加模式
            ]
            subprocess.run(cmd, capture_output=True, timeout=300)

            processed = min(i + batch_size, total)
            percent = (processed * 100) // total
            print(f"  进度：{percent}% ({processed}/{total})", end="\r")

        print()  # 换行
        # 清理临时文件
        if os.path.exists(os.path.join(project_path, ".ctags-batch")):
            os.remove(os.path.join(project_path, ".ctags-batch"))
    else:
        # 一次性构建
        cmd = [
            "ctags",
            "--languages=C,C++",
            "--c-kinds=+p",
            "--fields=+n",
            "-f", tags_file,
            "-L", filelist_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 and not os.path.exists(tags_file):
            print(f"ctags 失败：{result.stderr}", file=sys.stderr)
            return False

    print(f"  ctags: 完成 ({total} 文件)")

    # 3. 构建 cscope（一次性构建）
    if show_progress:
        print("\n[2/2] 构建 cscope 索引...")
    else:
        print("构建 cscope 索引...")

    cscope_filelist = os.path.join(project_path, ".cscope-files")
    cscope_out = os.path.join(project_path, "cscope.out")

    # 写入完整文件列表（相对路径）
    with open(cscope_filelist, "w") as f:
        for filepath in files:
            f.write(f"{filepath}\n")

    # cscope 在项目目录下运行，使用相对路径
    cmd = [
        "cscope",
        "-b",
        "-q",
        "-f", "cscope.out",  # 相对路径
        "-i", ".cscope-files",  # 相对路径
    ]

    if verbose:
        print(f"执行：{' '.join(cmd)} (cwd={project_path})")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=project_path)

        if verbose and result.stderr:
            print(f"cscope stderr: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("cscope 构建超时", file=sys.stderr)
        return False

    cscope_ok = os.path.exists(cscope_out)
    print(f"  cscope: {'完成' if cscope_ok else '失败'} ({total} 文件)")

    # 4. 验证
    tags_ok = os.path.exists(tags_file)

    print(f"\n索引构建完成!")
    print(f"  tags: {'✓' if tags_ok else '✗'}")
    print(f"  cscope: {'✓' if cscope_ok else '✗'}")

    return tags_ok and cscope_ok


def clean_index(project_path: str) -> bool:
    """删除索引文件"""
    index_files = [
        "tags",
        "cscope.out",
        "cscope.out.in",
        "cscope.out.po",
        ".ctags-files",
        ".cscope-files",
        ".ctags-batch",
    ]

    removed = []
    for filename in index_files:
        filepath = os.path.join(project_path, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            removed.append(filename)

    if removed:
        print(f"已删除索引文件:")
        for f in removed:
            print(f"  - {f}")
    else:
        print("没有找到索引文件")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="构建 C/C++ 代码索引 (ctags + cscope)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python build_index.py .                    # 当前目录
    python build_index.py /app/src             # 指定目录
    python build_index.py /app/src -v          # 详细模式
    python build_index.py /app/src --no-progress  # 不显示进度
    python build_index.py /app/src --clean     # 删除索引文件
        """,
    )

    parser.add_argument(
        "project_path",
        type=str,
        help="项目根目录路径",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细输出",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="不显示进度条",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="删除索引文件",
    )

    args = parser.parse_args()

    # 验证路径
    if not os.path.isdir(args.project_path):
        print(f"错误：目录不存在：{args.project_path}", file=sys.stderr)
        sys.exit(1)

    # 清理或构建
    if args.clean:
        clean_index(args.project_path)
    else:
        success = build_index_with_progress(
            args.project_path,
            verbose=args.verbose,
            show_progress=not args.no_progress,
        )
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
