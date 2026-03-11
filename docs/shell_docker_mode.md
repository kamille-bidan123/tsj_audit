# ShellTool Docker 模式支持

## 概述

`ShellTool` 现在支持本地模式和 Docker 模式，通过 `ToolExecutor` 的配置自动切换：

- **本地模式**：在宿主机创建 bash 进程和 session
- **Docker 模式**：在容器内执行命令，通过 `docker exec` 实现

## 配置方式

```python
from tools.executor import ToolExecutor

# 本地模式（默认）
ToolExecutor.set_local_mode()

# Docker 模式
ToolExecutor.set_docker_mode(
    container_id="my_container",
    workdir="/app",
)
```

## 命令对比

| 命令 | 本地模式 | Docker 模式 |
|------|---------|-----------|
| `run_command` | 在宿主机执行 | `docker exec <container> bash -c <cmd>` |
| `create_session` | 创建 pty bash 进程 | 记录容器 ID 和初始目录 |
| `session_exec` | 通过 pty 发送命令 | `docker exec <container> bash -c 'cd <cwd> && <cmd>'` |
| `list_sessions` | 显示进程状态 | 显示容器 ID 和 cwd |

## Docker 模式 Session 特性

### 1. 无状态 session

Docker 模式的 session 不创建实际进程，只记录：
- `container_id`: 容器 ID
- `cwd`: 当前工作目录

每个 `session_exec` 都是独立的 `docker exec` 调用，通过 `cd` 保持目录状态。

### 2. 目录保持

```python
ToolExecutor.set_docker_mode("my_container", "/app")

# 创建 session
ToolExecutor.call("create_session s1")
# cwd = /app

# 切换目录
ToolExecutor.call("session_exec s1 cd /app/src")
# 更新 cwd = /app/src

# 后续命令在新目录执行
ToolExecutor.call("session_exec s1 ls -la")
# 实际执行：docker exec my_container bash -c 'cd /app/src && ls -la'
```

### 3. 自动清理

Docker session 关闭时不需要终止进程，只需从注册表删除：

```python
ToolExecutor.call("close_session s1")
# 仅从 _sessions 删除，不影响容器
```

## 使用示例

### 示例 1：基本 Docker 命令执行

```python
from tools.executor import ToolExecutor

ToolExecutor.set_docker_mode("code_container", "/app")

# 临时命令
result = ToolExecutor.call("run_command ls -la")
print(result)

# 创建 session
ToolExecutor.call("create_session audit")

# 在 session 中执行
ToolExecutor.call("session_exec audit python -c 'import sys; print(sys.version)'")
ToolExecutor.call("session_exec audit pip install requests")
```

### 示例 2：代码审计场景

```python
from agents.code_audit_agent import CodeAuditAgent
from tools.executor import ToolExecutor

# 设置 Docker 环境
ToolExecutor.set_docker_mode("vulnerable_app", "/app/target")

# 创建审计 Agent
agent = CodeAuditAgent()

# LLM 调用工具
agent.handle_llm_response({
    "command": "create_session audit",
    "logic": "创建审计 session"
})

agent.handle_llm_response({
    "command": "session_exec audit grep -r 'eval(' .",
    "logic": "搜索危险的 eval 调用"
})

agent.handle_llm_response({
    "command": "session_exec audit python -c 'import ast; ...'",
    "logic": "执行 AST 分析"
})
```

### 示例 3：多 session 并发

```python
# 创建多个 session 用于不同任务
ToolExecutor.call("create_session build")
ToolExecutor.call("create_session test")
ToolExecutor.call("create_session analyze")

# 在不同 session 中执行不同任务
ToolExecutor.call("session_exec build python setup.py build")
ToolExecutor.call("session_exec test pytest tests/")
ToolExecutor.call("session_exec analyze python analyze.py")

# 查看状态
print(ToolExecutor.call("list_sessions"))
# 活跃 session 列表:
#   build [Docker: container] cwd: /app/build
#   test [Docker: container] cwd: /app/tests
#   analyze [Docker: container] cwd: /app/analyze
```

## 注意事项

### 1. 容器必须存在

Docker 模式要求指定的容器正在运行：

```python
# 错误示例：容器不存在
ToolExecutor.set_docker_mode("nonexistent", "/app")
result = ToolExecutor.call("run_command ls")
# 输出：Error response from daemon: No such container: nonexistent
```

### 2. 工作目录

确保 `workdir` 在容器内存在：

```python
ToolExecutor.set_docker_mode("my_container", "/app/code")
```

### 3. 权限和安全

Docker 容器内的命令执行权限取决于容器配置：
- 默认非 root 用户
- 某些系统命令可能受限
- 文件访问受容器挂载限制

### 4. 性能考虑

每个 `session_exec` 都是一次 `docker exec` 调用：
- 频繁小命令可能有延迟
- 建议合并命令：`cmd1 && cmd2`
- 长时命令注意超时设置

## API 参考

### ToolExecutor 配置

```python
# 本地模式
ToolExecutor.set_local_mode()

# Docker 模式
ToolExecutor.set_docker_mode(
    container_id: str,      # 容器 ID 或名称
    workdir: str = "/app",  # 容器内工作目录
)


```

### ShellTool 命令

```
# 临时命令
run_command <command>

# Session 管理
create_session [name]
session_exec <session_id> <command>
close_session <session_id>
list_sessions
```

## 与 FileTool 的一致性

`ShellTool` 和 `FileTool` 共享相同的配置机制：

```python
# 同时影响两个工具
ToolExecutor.set_docker_mode("container", "/app")

# FileTool: read_file 操作容器内文件
ToolExecutor.call("read_file src/main.py")

# ShellTool: 在容器内执行命令
ToolExecutor.call("run_command ls -la")
```

两者都对 LLM 透明，LLM 使用相同的命令格式。
