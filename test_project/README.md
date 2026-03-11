# CivetWeb 测试项目

这是一个包含多种安全漏洞的 CivetWeb 示例项目，用于测试代码审计工具。

## 项目结构

```
test_project/
├── CMakeLists.txt      # CMake 构建配置
├── main.c              # 主程序，包含多个漏洞处理函数
├── README.md           # 说明文档
└── www/                # 静态文件目录（可选）
```

## 编译方法

### 使用 CMake 编译

```bash
cd test_project

# 创建构建目录
mkdir build && cd build

# 配置项目（会自动拉取 CivetWeb 依赖）
cmake ..

# 编译
cmake --build .

# 或者使用 make
make
```

### 首次编译

首次编译时会自动从 GitHub 拉取 CivetWeb 源码，可能需要几分钟时间。

```bash
mkdir build && cd build
cmake ..
cmake --build .
```

## 安全漏洞列表

| 端点 | 函数 | 漏洞类型 | 危险函数 |
|------|------|----------|----------|
| /search | handle_search | SQL 注入 | sprintf |
| /system | handle_system | 命令注入 | system, sprintf |
| /file | handle_file | 路径遍历 | fopen, sprintf |
| /user | handle_user | 缓冲区溢出、格式化字符串 | strcpy, sprintf |
| /safe | handle_safe | 安全示例 (无漏洞) | snprintf |

## 运行服务器

```bash
# 启动服务器（监听 8080 端口）
./build/server

# 服务器启动后按 Enter 键停止
```

## 测试 URL

启动服务器后，可以使用以下 URL 进行测试：

```bash
# SQL 注入测试
curl "http://localhost:8080/search?q=test' OR '1'='1"

# 命令注入测试
curl "http://localhost:8080/system?action=ls%20-la"

# 路径遍历测试
curl "http://localhost:8080/file?name=../../../etc/passwd"

# 缓冲区溢出测试
curl "http://localhost:8080/user?name=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&email=test@example.com"

# 安全示例
curl "http://localhost:8080/safe?data=hello"
```

## 依赖

- CMake 3.14+
- GCC 或 Clang
- pthread 库
- Git（用于 FetchContent 拉取依赖）

## 注意事项

1. **仅用于测试**：此项目包含故意设计的安全漏洞，不应用于生产环境
2. **端口占用**：默认使用 8080 端口，如有冲突请修改代码中的端口号
3. **权限**：运行服务器可能需要适当的权限
