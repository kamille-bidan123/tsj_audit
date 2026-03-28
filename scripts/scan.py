#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CivetWeb URL 路由扫描脚本

扫描代码目录中的 mg_set_request_handler 调用，
以及 C++ 中继承自 CivetServer 的处理器类，
提取 URL 注册信息和对应的回调函数/方法。

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
ATTACK_SURFACE = "civetweb"

# 外部输入点说明（硬编码自 input.md）
INPUT_POINT = """# CivetWeb 外部输入点说明

## 概述

CivetWeb 是一个用 C 语言编写的嵌入式 Web 服务器。本文件描述了从外部请求到内部函数调用的数据流污染路径。

## 外部输入来源

### 1. HTTP 请求参数（C 和 C++ 通用）

通过 `mg_get_var`、`mg_get_header` 等函数获取的用户输入：

```c
// 查询参数
const char *query = mg_get_var(conn, "param_name");

// HTTP 头
const char *auth = mg_get_header(conn, "Authorization");

// POST 数据
char post_data[1024];
mg_read(conn, post_data, sizeof(post_data));

// Cookie
const char *cookie = mg_get_cookie(conn, "session_id");

// 表单变量
int len = mg_get_form_var(conn, "field_name", buffer, sizeof(buffer));
```

### 2. URL 路径参数

URL 路径本身可能包含用户控制的输入：

```c
// 请求的 URI
const char *uri = mg_get_request_info(conn)->request_uri;
const char *method = mg_get_request_info(conn)->request_method;
const char *query_string = mg_get_request_info(conn)->query_string;
```

### 3. 文件上传

通过 `mg_upload` 或直接读取请求体：

```c
// 文件上传
mg_upload(conn, "/tmp");

// 原始请求体
mg_read(conn, buffer, len);
```

### 4. WebSocket 输入（C++）

WebSocket 连接中的数据：

```cpp
// WebSocket 消息处理（在 CivetWeb 1.15+）
class WebSocketHandler : public CivetWebSocketHandler {
public:
    // 处理 WebSocket 消息
    bool handleMessage(CivetServer *server,
                       const WebSocketConnection *ws_con,
                       const char *data, size_t len) {
        // data 和 len 是用户可控的输入
        // ...
    }

    // 处理 WebSocket 连接
    bool handleConnection(CivetServer *server,
                          const WebSocketConnection *ws_con) {
        // ws_con 包含连接信息
        const char *uri = ws_con->request_uri;
        // ...
    }

    // 处理 WebSocket 关闭
    void handleClose(const WebSocketConnection *ws_con) {
        // 清理资源
    }
};
```

### 5. C++ 特有的输入处理

在 C++ 实现中，CivetServer 通常通过继承和重写方法来处理请求：

```cpp
class MyHandler : public CivetHandler {
public:
    bool handleGet(CivetServer *server, struct mg_connection *conn) {
        // 处理 GET 请求
        const char *uri = mg_get_request_info(conn)->request_uri;
        const char *query = mg_get_request_info(conn)->query_string;
        const char *param = mg_get_var(conn, "param");
        // ...
    }

    bool handlePost(CivetServer *server, struct mg_connection *conn) {
        // 处理 POST 请求
        char post_data[4096];
        int len = mg_read(conn, post_data, sizeof(post_data) - 1);
        post_data[len] = '\0';
        // ...
    }

    bool handleCivetHeader(CivetServer *server, struct mg_connection *conn,
                           const char *header, const char *value) {
        // 自定义头部处理，header 和 value 是用户可控的
        // ...
    }

    bool handleCivetVar(CivetServer *server, struct mg_connection *conn,
                        const char *var, const char *value) {
        // 模板变量处理，var 和 value 是用户可控的
        // ...
    }
};
```

### 6. JSON 请求体（C++）

```cpp
bool handlePost(CivetServer *server, struct mg_connection *conn) {
    // 读取整个请求体
    std::string body;
    char buf[4096];
    while (int len = mg_read(conn, buf, sizeof(buf) - 1)) {
        buf[len] = '\0';
        body += buf;
    }

    // 解析 JSON（需要外部库如 rapidjson 或 nlohmann/json）
    auto json = nlohmann::json::parse(body);  // body 完全用户可控
    // ...
}
```

### 7. multipart/form-data 文件上传（C++）

```cpp
bool handlePost(CivetServer *server, struct mg_connection *conn) {
    struct mg_form_data_handler fdh = {
        .field_found = [](struct mg_connection *conn, void *data,
                         const char *fieldname, const char *filename,
                         char *path, size_t pathlen) -> int {
            // fieldname, filename 完全用户可控
            // ...
            return 0;
        },
        .field_get = [](struct mg_connection *conn, void *data,
                       const char *name, const char *value,
                       size_t len) -> int {
            // name 和 value 完全用户可控
            // ...
            return 0;
        },
    };

    mg_handle_form_request(conn, &fdh);
    return true;
}
```

## 常见污染路径

### 路径 1: 参数 -> sprintf -> 缓冲区溢出
```c
char buffer[256];
const char *user_input = mg_get_var(conn, "name");
sprintf(buffer, "SELECT * FROM users WHERE name='%s'", user_input);  // SQL 注入
```

### 路径 2: 参数 -> system/exec -> 命令注入
```c
const char *cmd = mg_get_var(conn, "command");
char sys_cmd[512];
sprintf(sys_cmd, "ls -la %s", cmd);
system(sys_cmd);  // 命令注入
```

### 路径 3: 参数 -> 文件操作 -> 路径遍历
```c
const char *file = mg_get_var(conn, "filename");
char path[256];
sprintf(path, "/var/www/html/%s", file);
FILE *f = fopen(path, "r");  // 路径遍历
```

### 路径 4: WebSocket 数据 -> 命令执行（C++）
```cpp
bool handleMessage(CivetServer *server, const WebSocketConnection *ws_con,
                   const char *data, size_t len) {
    // data 完全用户可控
    system(data);  // 命令注入
}
```

### 路径 5: JSON body -> 命令注入（C++）
```cpp
auto json = nlohmann::json::parse(body);
std::string cmd = json["cmd"];  // 完全用户可控
system(cmd.c_str());
```

## 需要审计的函数模式

1. **直接用户输入使用**：`mg_get_var`, `mg_read`, `mg_get_header`, `mg_get_cookie`, `mg_get_form_var`
2. **字符串拼接**：`sprintf`, `strcat`, `strcpy`, `std::string +=`
3. **危险函数调用**：`system`, `exec*`, `popen`, `fopen`, `open`
4. **SQL 查询构造**：包含 SQL 关键字的字符串格式化
5. **C++ 中的请求处理**：`handleGet`, `handlePost`, `handlePut`, `handleDelete` 等
6. **WebSocket 处理**：`handleMessage` 中的 data 和 len 参数
7. **JSON 解析**：解析用户提供的 JSON 数据

## 示例输入点

| 函数/位置 | 输入类型 | 风险等级 |
|-----------|----------|----------|
| mg_get_var(conn, "*") | GET/POST 参数 | 高 |
| mg_get_header(conn, "*") | HTTP 头 | 中 |
| mg_get_cookie(conn, "*") | Cookie | 中 |
| mg_read(conn, buf, len) | 请求体 | 高 |
| mg_get_request_info(conn) | URI/Method | 中 |
| handleGet/handlePost | HTTP 请求 | 高 |
| handleMessage(data, len) | WebSocket 数据 | 高 |
| JSON 解析后 | JSON body | 高 |
"""

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

# C++ 中 CivetHandler 派生类的模式
CIVETSERVER_HANDLER_PATTERN = re.compile(
    r'(class\s+(\w+)\s*:\s*public\s+Civet(?:Request)?Handler|'
    r'struct\s+(\w+)\s*:\s*public\s+Civet(?:Request)?Handler)',
    re.MULTILINE
)

# C++ 中请求处理方法的模式
REQUEST_METHOD_PATTERNS = [
    # 匹配各种 handle 方法，包括重写版本
    re.compile(r'(handleGet|handlePost|handlePut|handleDelete|handlePatch|handleHead|handleOptions)\s*\(\s*CivetServer\s*\*\s*\w*\s*,\s*struct\s*mg_connection\s*\*\s*\w*\s*\)'),
    # 匹配 operator() 如果被重载
    re.compile(r'operator\(\)\s*\(\s*CivetServer\s*\*\s*\w*\s*,\s*struct\s*mg_connection\s*\*\s*\w*\s*\)'),
    # 匹配一般的请求处理函数，如果它们接受 CivetServer* 和 mg_connection* 参数
    re.compile(r'(\w+)\s*\(\s*CivetServer\s*\*\s*\w*\s*,\s*struct\s*mg_connection\s*\*\s*\w*\s*\)')
]

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
    """从文件内容中提取函数定义代码片段和行号

    Args:
        content: 文件内容
        func_name: 函数名
        start_pos: 开始搜索的位置

    Returns:
        tuple: (code_snippet, start_line, end_line)
    """
    # 对于 C++ 方法，尝试匹配完整的方法定义
    if func_name in ['handleGet', 'handlePost', 'handlePut', 'handleDelete', 'handlePatch', 'handleHead', 'handleOptions']:
        # 匹配 handle 方法的实现，特别是 ClassName::methodName 形式
        pattern = re.compile(
            rf'(\w+)::({func_name})\s*\([^)]*\)\s*{{',
            re.MULTILINE
        )

        # 首先尝试命名空间限定的版本
        match = pattern.search(content, start_pos)
        if not match:
            # 尝试普通方法定义
            pattern = re.compile(
                rf'({func_name})\s*\([^)]*\)\s*{{',
                re.MULTILINE
            )
            match = pattern.search(content, start_pos)
    else:
        # 匹配函数定义：返回类型 函数名 (参数) { ... }
        pattern = re.compile(
            r'(?:static\s+)?(?:void|int|char\s*\*?|struct\s+\w+|\w+)\s*\*?\s*'
            rf'{re.escape(func_name)}\s*\([^)]*\)',
            re.MULTILINE
        )
        match = pattern.search(content, start_pos)

    if not match:
        return ("", 0, 0)

    # 计算起始行号（从 1 开始）
    func_start_pos = match.start()
    start_line = content[:func_start_pos].count('\n') + 1

    # 找到函数体开始位置
    brace_start = content.find('{', match.end() - 1)
    if brace_start == -1:
        # 没有函数体，返回声明
        end = content.find(';', match.end())
        if end == -1:
            end = len(content)
        else:
            end += 1
        end_line = content[:end].count('\n') + 1

        # 提取声明行
        declaration_start = content.rfind('\n', 0, match.start())
        if declaration_start == -1:
            declaration_start = 0
        else:
            declaration_start += 1

        declaration_end = content.find('\n', match.end())
        if declaration_end == -1:
            declaration_end = len(content)

        snippet_lines = content[declaration_start:declaration_end].split('\n')
        code_with_lines = []
        for i, line in enumerate(snippet_lines):
            if line.strip():  # 只处理非空行
                line_num = start_line + i
                code_with_lines.append(f"{line_num}: {line}")

        code_snippet = '\n'.join(code_with_lines)
        return (code_snippet, start_line, end_line)

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

    # 提取代码片段，带行号
    snippet_content = content[func_start_pos:end_pos]
    snippet_lines = snippet_content.split('\n')
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


def scan_cpp_handlers(content: str, file_path: str, project_path: str) -> List[Dict]:
    """扫描 C++ 代码中的 CivetHandler 派生类和处理方法"""
    results = []

    # 查找所有 CivetHandler 派生类
    handler_classes = CIVETSERVER_HANDLER_PATTERN.findall(content)

    # 存储已发现的类名，避免重复处理
    processed_classes = set()

    for class_match in handler_classes:
        # 提取类名 - 类名在第一个或第三个捕获组中
        class_name = class_match[1] if class_match[1] else class_match[2]

        # 如果已处理过这个类，则跳过
        if class_name in processed_classes:
            continue

        processed_classes.add(class_name)

        # 查找此类的所有方法
        for method_pattern in REQUEST_METHOD_PATTERNS:
            method_matches = list(method_pattern.finditer(content))

            for method_match in method_matches:
                method_name = method_match.group(1) if method_match.lastindex >= 1 else "unknown"

                # 构造完整的方法名（包含类名）
                full_method_name = f"{class_name}::{method_name}"

                # 首先检查是否已经有相同的方法添加到结果中
                existing_result = next((r for r in results if r['callback_func'] == full_method_name and r['file_path'] == str(file_path.relative_to(project_path))), None)
                if existing_result:
                    continue

                # 提取方法实现
                method_start_pos = method_match.start()
                code_snippet, start_line, end_line = extract_function_definition(content, method_name, method_start_pos)

                if start_line == 0:  # 如果没找到具体实现，尝试查找方法声明
                    # 尝试匹配类定义内的方法声明
                    class_pattern = re.compile(rf'class\s+{class_name}\s*{{([^}}]*)}}', re.MULTILINE | re.DOTALL)
                    class_match_obj = class_pattern.search(content)

                    if class_match_obj:
                        class_content = class_match_obj.group(1)
                        # 在类定义中查找对应方法
                        method_decl_pattern = re.compile(rf'{method_name}\s*\([^)]*\)\s*[^{{}};]*[{{;]')
                        method_decl_match = method_decl_pattern.search(class_content)

                        if method_decl_match:
                            method_start_pos = class_match_obj.start() + method_decl_match.start()
                            snippet_start_line = content[:method_start_pos].count('\n') + 1

                            # 提取一行作为代码片段
                            line_start = content.rfind('\n', 0, method_start_pos)
                            if line_start == -1:
                                line_start = 0
                            else:
                                line_start += 1

                            line_end = content.find('\n', method_start_pos)
                            if line_end == -1:
                                line_end = len(content)

                            snippet = content[line_start:line_end]
                            code_snippet = f"{snippet_start_line}: {snippet.strip()}"
                            start_line = snippet_start_line
                            end_line = snippet_start_line

                # 构造 URL 路径
                url_path = f"/{class_name}"

                # 尝试从注释中获取更精确的路径
                comment_pattern = re.compile(rf'//\s*@path\s+([^\s]+)|/\*\s*@path\s+([^\s]+)\s*\*/', re.IGNORECASE)
                comment_matches = list(comment_pattern.finditer(content))
                for comment_match in comment_matches:
                    # 如果注释紧跟在函数定义前，认为是针对此函数的注释
                    comment_pos = comment_match.start()
                    if method_start_pos - 100 <= comment_pos <= method_start_pos:
                        matched_path = comment_match.group(1) or comment_match.group(2)
                        if matched_path:
                            url_path = matched_path
                        break
                else:
                    # 尝试从类注释中获取路径
                    class_comment_pattern = re.compile(rf'class\s+{class_name}\s*/\*\*(.*?)\*/', re.DOTALL)
                    class_comments = class_comment_pattern.findall(content)
                    for comment in class_comments:
                        path_match = re.search(r'@path\s+([^\s]+)', comment, re.IGNORECASE)
                        if path_match:
                            url_path = path_match.group(1)
                            break

                if start_line != 0:  # 只有找到了相关信息才添加到结果中
                    rel_path = str(file_path.relative_to(project_path))
                    results.append({
                        "url_path": url_path,
                        "callback_func": full_method_name,
                        "file_path": rel_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "code_snippet": code_snippet,
                    })

    return results


def scan_file(filepath: Path, project_path: str) -> List[Dict]:
    """扫描单个文件，查找 mg_set_request_handler 调用和 C++ CivetHandler"""
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

        # 检查是否已经有相同的结果
        existing_result = next((r for r in results if r['callback_func'] == callback_func and r['file_path'] == rel_path), None)
        if existing_result:
            continue

        # 提取回调函数定义（带行号）
        code_snippet, start_line, end_line = find_code_snippet(content, callback_func)

        if start_line != 0:  # 确保找到了函数定义
            results.append({
                "url_path": url_path,
                "callback_func": callback_func,
                "file_path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
                "code_snippet": code_snippet,
            })

    # 检查 C++ 处理器
    cpp_results = scan_cpp_handlers(content, filepath, project_path)
    results.extend(cpp_results)

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

    # 用于跟踪已发现的函数，避免重复
    seen_functions = set()

    for i, file in enumerate(files, 1):
        filepath = project / file
        file_results = scan_file(filepath, project_path)

        for r in file_results:
            # 创建唯一标识符，用于去重
            func_identifier = (r["callback_func"], r["file_path"], r["start_line"])

            if func_identifier in seen_functions:
                continue

            seen_functions.add(func_identifier)

            func_info = FunctionInfo(
                func_name=r["callback_func"],
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                code_snippet=r["code_snippet"],
                input=INPUT_POINT,
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
        # 确保中文字符不被转义，设置 ensure_ascii=False
        print(json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False))
    else:
        # 文本格式
        if not results:
            print("未找到 mg_set_request_handler 调用或 C++ CivetHandler 实现")
            return

        print(f"\n共找到 {len(results)} 个 URL 路由注册:\n")
        print("-" * 80)

        for i, r in enumerate(results, 1):
            print(f"[{i}] {r.func_name}")
            print(f"    文件：{r.file_path}:{r.start_line}-{r.end_line}")
            if r.code_snippet:
                print(f"    代码片段:")
                for line in r.code_snippet.split('\n')[:10]:
                    print(f"        {line}")
            print("-" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="扫描 CivetWeb URL 路由注册 (mg_set_request_handler 和 C++ CivetHandler)",
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