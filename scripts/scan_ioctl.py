#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ioctl 接口扫描脚本

扫描代码目录中的 ioctl 处理函数，
提取 unlocked_ioctl 和 proc_ioctl 接口定义。

用法:
    python scan_ioctl.py <code_directory>

示例:
    python scan_ioctl.py .
    python scan_ioctl.py /app/src
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

# 项目类型和攻击面（硬编码）
PROJECT_TYPE = "c"
ATTACK_SURFACE = "ioctl"

# 外部输入点说明
INPUT_POINT = """# ioctl 外部输入点说明

## 概述

ioctl（I/O Control）是 Linux/Unix 系统调用，用于与设备驱动进行交互。
本文件描述了 ioctl 接口的数据流污染路径。

## 外部输入来源（全部来自用户空间）

### 1. ioctl() 系统调用参数

**所有参数都来自用户态，完全用户可控：**

```c
#include <sys/ioctl.h>

int fd = open("/dev/mydevice", O_RDWR);
int ret = ioctl(fd, MY_CMD, &arg);
```

**参数说明：**
- `fd`：通过 open() 打开的设备文件描述符（用户态传入）
- `cmd`：ioctl 命令码，**用户态直接传入，可控**
- `arg`：指向用户空间的指针，**用户态数据，可控**
  - 可以是整数（作为值传递）
  - 可以是指向用户空间缓冲区的指针（数据在这里）

### 2. unlocked_ioctl 处理函数

Linux 2.6.36+ 内核使用 unlocked_ioctl：

```c
#include <linux/fs.h>

static long mydev_unlocked_ioctl(struct file *filp,
                                unsigned int cmd,    // 用户态传入，完全可控
                                unsigned long arg) { // 用户态传入，完全可控
    // cmd 和 arg 都是外部输入
}
```

**输入来源：**
- `cmd`：用户态直接传入的整数值
- `arg`：用户态传入的指针或整数值

### 3. proc_ioctl 处理函数

/proc 接口的 ioctl 处理：

```c
#include <linux/proc_fs.h>

static int myproc_ioctl(struct file *filp,
                        unsigned int cmd,    // 用户态传入
                        unsigned long arg) { // 用户态传入
}
```

## 内核与用户空间数据交互函数

### 1. copy_from_user

**作用**：从用户空间拷贝数据到内核空间
**输入**：用户态提供的缓冲区地址和数据

```c
// 原型
unsigned long copy_from_user(void *to, const void __user *from, unsigned long n);

// 示例
struct mystruct data;
copy_from_user(&data, (void __user *)arg, sizeof(data));
//                        ^^^^^^^^^^^^^^
//                        用户态地址，数据来自用户空间
```

**风险**：如果用户态数据未验证，可能导致：
- 缓冲区溢出
- 任意内存写

### 2. copy_to_user

**作用**：从内核空间拷贝数据到用户空间

```c
// 原型
unsigned long copy_to_user(void __user *to, const void *from, unsigned long n);

// 示例
struct mystruct result;
copy_to_user((void __user *)arg, &result, sizeof(result));
```

**风险**：
- 泄露内核数据

### 3. get_user / __get_user

**作用**：从用户空间读取单个值

```c
// 原型
int get_user(x, ptr);    // 宏版本
int __get_user(x, ptr);  // 内联函数版本

// 示例
int val;
get_user(val, (int __user *)arg);  // 读取用户态的 int 值
```

### 4. put_user / __put_user

**作用**：向用户空间写入单个值

```c
// 原型
int put_user(x, ptr);    // 宏版本
int __put_user(x, ptr);  // 内联函数版本

// 示例
int result = 123;
put_user(result, (int __user *)arg);  // 写入用户态
```

### 5. access_ok

**作用**：验证用户空间指针是否可访问

```c
// 原型
bool access_ok(int type, const void *addr, size_t size);

// 示例
if (!access_ok(VERIFY_WRITE, arg, sizeof(data)))
    return -EFAULT;
```

## 常见污染路径

### 路径 1: ioctl arg -> copy_from_user -> 内核使用

```c
static long mydev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg) {
    struct mystruct data;
    // arg 来自用户态，copy_from_user 从用户空间拷贝数据
    copy_from_user(&data, (void __user *)arg, sizeof(data));

    // 如果 data 包含指针或未验证成员，可能导致任意内存读写
    memcpy(kernel_buffer, data.ptr, data.len);  // 危险！
}
```

**风险**：
- 任意内存读写
- 缓冲区溢出
- 拒绝服务

### 路径 2: 未验证的 cmd 命令码

```c
static long mydev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg) {
    // cmd 完全用户可控
    switch (cmd) {
        case CMD1: return cmd1_handler(arg);
        case CMD2: return cmd2_handler(arg);
        // 如果缺少 default 或验证，可能导致越界访问
    }
}
```

**风险**：
- 数组越界
- 内存泄露

### 路径 3: get_user 直接使用

```c
static long mydev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg) {
    int user_val;
    get_user(user_val, (int __user *)arg);  // 从用户态读取

    // 直接使用未验证的值
    if (user_val > MAX_SIZE) { /* 可能导致问题 */ }
    memcpy(buf, src, user_val);  // 危险！
}
```

### 路径 4: 竞态条件（TOCTOU）

```c
static long mydev_ioctl(struct file *filp, unsigned int cmd, unsigned long arg) {
    if (!access_ok(VERIFY_WRITE, arg, sizeof(data))) return -EFAULT;
    copy_from_user(&data, (void __user *)arg, sizeof(data));

    // 检查和使用之间可能被其他线程修改
    copy_to_user((void __user *)arg, &result, sizeof(result));
}
```

## 需要审计的函数模式

### 1. ioctl 处理函数
- `unlocked_ioctl` 的 cmd 和 arg 参数
- `proc_ioctl` 的 cmd 和 arg 参数

### 2. 数据传输（审计这些函数的调用上下文）
- `copy_from_user` - 从用户空间读取
- `copy_to_user` - 写入用户空间
- `get_user` / `__get_user` - 读取单个值
- `put_user` / `__put_user` - 写入单个值
- `access_ok` - 指针验证

### 3. 常见危险模式
- 未验证的用户数据直接使用
- 指针类型未正确转换
- 缺少 access_ok 检查
- 整数溢出

## 示例输入点

| 位置 | 输入类型 | 说明 |
|------|----------|------|
| unlocked_ioctl(cmd, arg) | cmd 和 arg | 完全用户可控 |
| proc_ioctl(cmd, arg) | cmd 和 arg | 完全用户可控 |
| copy_from_user(..., arg, ...) | 用户态数据 | 来自用户空间 |
| get_user(..., arg) | 用户态数据 | 来自用户空间 |
| arg (强制类型转换后) | 用户态指针 | 指向用户空间 |
"""


# unlocked_ioctl 处理函数定义
UNLOCKED_IOCTL_PATTERN = re.compile(
    r'(?:static\s+)?(?:long|int)\s+(\w+)\s*\([^)]*\)\s*\{[^}]*unlocked_ioctl',
    re.MULTILINE | re.DOTALL
)

# proc_ioctl 处理函数定义
PROC_IOCTL_PATTERN = re.compile(
    r'(?:static\s+)?(?:long|int)\s+(\w+)\s*\([^)]*\)\s*\{[^}]*proc_ioctl',
    re.MULTILINE | re.DOTALL
)

# 直接匹配 unlocked_ioctl 函数名
UNLOCKED_IOCTL_NAME = re.compile(
    r'(?:static\s+)?(?:long|int)\s+(\w*unlocked_ioctl\w*)\s*\(',
    re.MULTILINE
)

# 直接匹配 proc_ioctl 函数名
PROC_IOCTL_NAME = re.compile(
    r'(?:static\s+)?(?:long|int)\s+(\w*proc_ioctl\w*)\s*\(',
    re.MULTILINE
)

# file_operations 结构体中的 unlocked_ioctl 成员
FILE_OPS_PATTERN = re.compile(
    r'\.unlocked_ioctl\s*=\s*(\w+)',
    re.MULTILINE
)

# proc_ops 结构体中的 proc_ioctl 成员
PROC_OPS_PATTERN = re.compile(
    r'\.proc_ioctl\s*=\s*(\w+)',
    re.MULTILINE
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


def extract_function_definition(content: str, func_name: str, start_pos: int = 0) -> tuple:
    """从文件内容中提取函数定义代码片段和行号"""
    # 匹配函数定义
    pattern = re.compile(
        r'(?:static\s+)?(?:void|int|long|unsigned|char\s*\*?|struct\s+\w+|\w+)\s*\*?\s*'
        rf'{re.escape(func_name)}\s*\([^)]*\)',
        re.MULTILINE
    )
    match = pattern.search(content, start_pos)

    if not match:
        return ("", 0, 0)

    # 计算起始行号
    func_start_pos = match.start()
    start_line = content[:func_start_pos].count('\n') + 1

    # 找到匹配的闭合括号
    brace_start = content.find('{', match.end() - 1)
    if brace_start == -1:
        # 没有函数体，返回声明
        end = content.find(';', match.end())
        if end == -1:
            end = len(content)
        else:
            end += 1
        end_line = content[:end].count('\n') + 1
        snippet_start = content.rfind('\n', 0, match.start()) + 1
        snippet_end = content.find('\n', match.end())
        if snippet_end == -1:
            snippet_end = len(content)
        code_snippet = content[snippet_start:snippet_end]
        return (f"{start_line}: {code_snippet}", start_line, end_line)

    # 找到匹配的闭合括号
    brace_count = 1
    pos = brace_start + 1
    while pos < len(content) and brace_count > 0:
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1

    end_pos = pos
    end_line = content[:end_pos].count('\n') + 1

    # 提取代码片段
    snippet_content = content[func_start_pos:end_pos]
    snippet_lines = snippet_content.split('\n')

    # 限制返回的代码长度（最多 15 行）
    if len(snippet_lines) > 15:
        snippet_lines = snippet_lines[:15]
        snippet_content = '\n'.join(snippet_lines) + '\n    // ... (truncated)'
        end_line = start_line + 14

    # 添加行号
    code_with_lines = []
    for i, line in enumerate(snippet_lines):
        line_num = start_line + i
        code_with_lines.append(f"{line_num}: {line}")

    code_snippet = '\n'.join(code_with_lines)

    return (code_snippet, start_line, end_line)


def scan_file(filepath: Path, project_path: str) -> List[Dict]:
    """扫描单个文件，查找 ioctl 处理函数"""
    results = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"警告：无法读取文件 {filepath}: {e}", file=sys.stderr)
        return results

    # 获取相对路径
    rel_path = str(filepath.relative_to(project_path))

    # 1. 查找 unlocked_ioctl 处理函数定义
    for match in UNLOCKED_IOCTL_NAME.finditer(content):
        func_name = match.group(1)
        code_snippet, start_line, end_line = extract_function_definition(content, func_name)
        if start_line != 0:
            results.append({
                "type": "unlocked_ioctl",
                "name": func_name,
                "file_path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
                "code_snippet": code_snippet,
            })

    # 2. 查找 proc_ioctl 处理函数定义
    for match in PROC_IOCTL_NAME.finditer(content):
        func_name = match.group(1)
        code_snippet, start_line, end_line = extract_function_definition(content, func_name)
        if start_line != 0:
            results.append({
                "type": "proc_ioctl",
                "name": func_name,
                "file_path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
                "code_snippet": code_snippet,
            })

    # 3. 查找 file_operations 中的 unlocked_ioctl 成员（可选，找到对应函数名）
    for match in FILE_OPS_PATTERN.finditer(content):
        func_name = match.group(1)
        start_line = content[:match.start()].count('\n') + 1
        snippet_start = content.rfind('\n', 0, match.start()) + 1
        snippet_end = content.find('\n', match.end())
        if snippet_end == -1:
            snippet_end = len(content)
        code_snippet = f"{start_line}: {content[snippet_start:snippet_end].strip()}"

        results.append({
            "type": "file_ops_registration",
            "name": f".unlocked_ioctl = {func_name}",
            "file_path": rel_path,
            "start_line": start_line,
            "end_line": start_line,
            "code_snippet": code_snippet,
        })

    # 4. 查找 proc_ops 中的 proc_ioctl 成员
    for match in PROC_OPS_PATTERN.finditer(content):
        func_name = match.group(1)
        start_line = content[:match.start()].count('\n') + 1
        snippet_start = content.rfind('\n', 0, match.start()) + 1
        snippet_end = content.find('\n', match.end())
        if snippet_end == -1:
            snippet_end = len(content)
        code_snippet = f"{start_line}: {content[snippet_start:snippet_end].strip()}"

        results.append({
            "type": "proc_ops_registration",
            "name": f".proc_ioctl = {func_name}",
            "file_path": rel_path,
            "start_line": start_line,
            "end_line": start_line,
            "code_snippet": code_snippet,
        })

    return results


def scan_directory(project_path: str) -> List[FunctionInfo]:
    """扫描整个目录，收集所有 ioctl 接口信息"""
    results = []
    project = Path(project_path)

    files = find_source_files(project_path)
    total = len(files)

    print(f"扫描目录：{project_path}")
    print(f"找到 {total} 个 C/C++ 文件")
    print(f"Project Type: {PROJECT_TYPE}, Attack Surface: {ATTACK_SURFACE}")
    print()

    # 用于跟踪已发现的函数，避免重复
    seen_functions = set()

    for i, file in enumerate(files, 1):
        filepath = project / file
        file_results = scan_file(filepath, project_path)

        for r in file_results:
            # 创建唯一标识符
            func_identifier = (r["name"], r["type"], r["file_path"], r["start_line"])

            if func_identifier in seen_functions:
                continue

            seen_functions.add(func_identifier)

            func_info = FunctionInfo(
                func_name=r["name"],
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                code_snippet=r["code_snippet"],
                input=INPUT_POINT,
            )
            results.append(func_info)

            type_label = {
                "unlocked_ioctl": "unlocked_ioctl",
                "proc_ioctl": "proc_ioctl",
                "file_ops_registration": "fops注册",
                "proc_ops_registration": "pops注册",
            }.get(r["type"], r["type"])

            print(f"  [{i}/{total}] 发现 {type_label}: {r['name']} @ {r['file_path']}:{r['start_line']}")

        # 显示进度
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
        # 文本格式
        if not results:
            print("未找到 unlocked_ioctl 或 proc_ioctl 处理函数")
            return

        print(f"\n共找到 {len(results)} 个 ioctl 处理函数:\n")
        print("-" * 80)

        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.func_name}")
            print(f"    文件：{r.file_path}:{r.start_line}-{r.end_line}")
            if r.code_snippet:
                print(f"    代码片段:")
                for line in r.code_snippet.split('\n')[:8]:
                    print(f"        {line}")
            print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="扫描 ioctl 处理函数 (unlocked_ioctl 和 proc_ioctl)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python scan_ioctl.py .                           # 扫描当前目录
    python scan_ioctl.py /app/src                    # 扫描指定目录
    python scan_ioctl.py /app/src -f json            # JSON 格式输出
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