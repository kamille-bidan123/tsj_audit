# TagsTool 使用文档

## 概述

`TagsTool` 使用 `ctags` 和 `cscope` 提供代码导航功能：
- `go_to_def <symbol>` - 跳转到符号定义
- `find_refs <symbol>` - 查找符号引用
- `list_symbols [pattern]` - 列出符号

## 使用前准备

在使用 `go_to_def`、`find_refs` 等命令前，需要先构建代码索引。

运行以下命令构建索引：

```bash
# 构建当前目录的索引
python scripts/build_index.py .

# 构建指定目录的索引
python scripts/build_index.py /app/src

# 详细模式
python scripts/build_index.py /app/src -v

# 不显示进度条
python scripts/build_index.py /app/src --no-progress
```

索引构建完成后，会在项目目录生成以下文件：
- `tags` - ctags 生成的符号索引
- `cscope.out` - cscope 数据库
- `cscope.in.out` - cscope 反向索引
- `cscope.po.out` - cscope 交叉引用索引
- `.cscope-files` - 需要索引的文件列表

这些文件可以安全删除，需要时重新运行构建脚本即可。

### go_to_def

跳转到符号定义处，返回定义所在的文件和行号。

```bash
# 查找 main 函数定义
go_to_def main

# 查找结构体定义
go_to_def struct_name

# 查找函数定义
go_to_def open_file
```

**返回格式：**
```
/path/to/file.c:line_number
```

如果有多个定义，每行返回一个。

### find_refs

查找符号的所有引用（定义 + 调用）。

```bash
# 查找 main 的引用
find_refs main

# 查找 hello 函数的引用
find_refs hello
```

**返回格式：**
```
/path/to/file.c:line_number: 代码内容
```

### list_symbols

列出索引中的符号。

```bash
# 列出所有符号
list_symbols

# 模糊搜索
list_symbols open

# 搜索特定模式
list_symbols init
```

## 使用示例

### 代码审计流程

```bash
# 1. 构建索引
python scripts/build_index.py /app/vulnerable_code

# 2. 查找危险函数定义
ToolExecutor.call("go_to_def strcpy")

# 3. 查找所有使用位置
ToolExecutor.call("find_refs strcpy")

# 4. 查看所有相关符号
ToolExecutor.call("list_symbols str")
```

### LLM 调用示例

```json
{
    "command": "go_to_def main",
    "logic": "查找程序入口点"
}
```

```json
{
    "command": "find_refs unsafe_function",
    "logic": "查找不安全函数的所有调用位置"
}
```

```json
{
    "command": "list_symbols vuln",
    "logic": "搜索包含 vuln 的符号，查找可能的漏洞相关代码"
}
```

## 依赖

需要安装以下工具：

```bash
# macOS
brew install universal-ctags cscope

# Ubuntu/Debian
apt install universal-ctags cscope

# Arch
pacman -S universal-ctags cscope
```

## 支持的语言

目前主要支持 C/C++ 代码，通过修改 `--languages` 选项可以扩展支持：
- C
- C++
- 其他 ctags/cscope 支持的语言

## 索引文件

运行构建脚本后会生成索引文件，详见上方"使用前准备"章节。

## 注意事项

1. **大型项目**：索引生成可能需要较长时间，建议设置合适的 timeout
2. **构建目录**：自动跳过 `build`、`node_modules` 等目录
3. **隐藏目录**：自动跳过以 `.` 开头的隐藏目录
4. **符号匹配**：支持精确匹配和前缀匹配（如 `main` 可以匹配 `main` 和 `main_loop`）

## 故障排除

### 未找到符号

确保已运行构建脚本：
```bash
python scripts/build_index.py .
```

如果索引不存在，工具会返回错误提示：
```
错误：索引不存在，请先运行 python scripts/build_index.py 构建索引
```

### ctags 失败

检查项目路径是否正确，是否有读取权限：
```bash
ls -la /path/to/project
```

### cscope 找不到文件

检查 `.cscope-files` 是否为空，项目中是否有 C/C++ 源文件。
