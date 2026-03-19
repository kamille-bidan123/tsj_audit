# CivetWeb 记事本应用

这是一个基于 CivetWeb 的记事本 Web 应用，采用 C 语言开发，包含 Web 服务进程和业务处理进程（Worker）。

## 项目架构

```
test_project/
├── src/
│   ├── main_web.c        # Web 服务进程（HTTP 请求处理）
│   ├── main_worker.c     # Worker 进程（业务逻辑处理）
│   ├── db.c/db.h         # SQLite 数据库模块
│   ├── rpc.c/rpc.h       # 进程间通信（RPC）模块
│   ├── utils.c/utils.h   # 工具函数模块
│   └── note_logic.c      # 笔记业务逻辑模块
├── www/                  # Web 静态文件
│   ├── index.html        # 主页面
│   └── app.js            # 前端 JavaScript
├── CMakeLists.txt        # CMake 构建配置
├── scan.py               # 扫描脚本（审计用）
└── README.md             # 本文档
```

### 进程架构

```
┌─────────────────┐     RPC      ┌─────────────────┐
│  Web Process    │ ──────────>  │  Worker Process │
│  (CivetWeb)     │   FIFO       │  (Business Log) │
│  - HTTP parsing │               │  - Database     │
│  - Routing      │               │  - RPC Handler  │
│  - Response     │               │  - Logic        │
└─────────────────┘               └─────────────────┘
```

## 功能特性

1. **用户认证**
   - 用户注册
   - 用户登录
   - 密码重置功能

2. **笔记管理**
   - 创建笔记
   - 读取笔记列表
   - 编辑笔记
   - 删除笔记（软删除/硬删除）

3. **FTP 同步**
   - 配置 FTP 服务器信息
   - 将笔记上传到 FTP 服务器

## 内置安全漏洞

| 端点 | 函数 | 漏洞类型 | 危险函数 |
|------|------|----------|----------|
| `/reset_password` | handle_reset_password | 权限绕过 | 无密码验证直接重置 |
| `/ftp/upload` | handle_upload_notes | 命令注入 | system(), sprintf |
| `/logo/upload` | handle_upload_logo | 路径穿越 | fopen, sprintf |
| `/login` | handle_login | 暴力破解 | 无频率限制 |

### 漏洞详情

1. **忘记密码漏洞**
   - 前端要求输入旧密码，但后端两个接口：一个验证旧密码（返回成功），一个直接重置密码（不验证）
   - 任意用户可以重置任意用户的密码

2. **登录暴力破解**
   - 前端有 3 次错误锁定机制
   - 后端没有真正的频率限制检查

3. **路径穿越漏洞**
   - logo 上传接口直接拼接用户输入的文件名
   - 可以上传任意文件到任意目录

4. **命令注入漏洞**
   - FTP 上传前会用 `system()` 拼接 IP 地址做 ping 测试
   - 可以注入命令：`192.168.1.1; cat /etc/passwd`

## 编译方法

```bash
cd test_project

# 创建构建目录
mkdir -p build && cd build

# 配置项目
cmake ..

# 编译
cmake --build .
```

或者使用 make：

```bash
mkdir -p build && cd build
cmake ..
make
```

## 运行应用

### 方式一：分别启动 Web 和 Worker 进程

```bash
# 启动 Worker 进程（在后台）
./build/notes_worker &

# 启动 Web 服务（在前台）
./build/notes_web
```

### 方式二：使用启动脚本

```bash
# 启动所有服务
./scripts/start.sh

# 停止所有服务
./scripts/stop.sh
```

## 访问地址

- Web 服务：http://localhost:8081
- 默认用户：admin（密码需要在数据库中设置）

## API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | /login | 用户登录 |
| POST | /register | 用户注册 |
| POST | /check_old_password | 验证旧密码（漏洞） |
| POST | /reset_password | 重置密码（漏洞） |
| GET | /notes | 获取笔记列表 |
| POST | /notes | 创建笔记 |
| POST | /notes/delete | 删除笔记 |
| GET | /ftp/config | 获取 FTP 配置 |
| POST | /ftp/save | 保存 FTP 配置 |
| POST | /ftp/upload | 上传笔记到 FTP（漏洞） |
| POST | /logo/upload | 上传 logo（漏洞） |

## 审计测试

使用 audit 工具进行审计：

```bash
cd /path/to/tsj_audit

python main.py \
    --api-key YOUR_API_KEY \
    --project-path ./test_project \
    --output-dir ./audit_results \
    --scan ./test_project/scan.py \
    --resume
```

## 数据库

数据库文件位于 `./notes.db`，包含以下表：

- `users` - 用户表
- `notes` - 笔记表
- `ftp_configs` - FTP 配置表

## 依赖

- CMake 3.14+
- GCC 或 Clang
- SQLite3
- CivetWeb
- pthread

## 注意事项

1. **仅用于测试**：此项目包含故意设计的安全漏洞，不应用于生产环境
2. **端口占用**：Web 服务默认使用 8081 端口
3. **权限**：运行服务器需要适当的文件读写权限
