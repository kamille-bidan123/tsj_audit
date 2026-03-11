# Shell Session 使用示例

## 命令列表

| 命令 | 说明 | 示例 |
|------|------|------|
| `run_command` | 执行一次性命令 | `run_command ls -la` |
| `create_session` | 创建持久 session | `create_session build` |
| `session_exec` | 在 session 中执行命令 | `session_exec build cd /app` |
| `close_session` | 关闭 session | `close_session build` |
| `list_sessions` | 列出所有 session | `list_sessions` |

## 基本使用

### 临时执行命令

```python
from tools.executor import ToolExecutor

# 执行一次性命令（类似 subprocess）
result = ToolExecutor.call("run_command ls -la")
print(result)

result = ToolExecutor.call("run_command git status")
print(result)
```

### 使用持久 Session

```python
# 创建 session
ToolExecutor.call("create_session my_session")

# 在 session 中执行命令（保持状态）
ToolExecutor.call("session_exec my_session cd /app/src")
ToolExecutor.call("session_exec my_session python build.py")
ToolExecutor.call("session_exec my_session ls -la")

# 查看 session 状态
result = ToolExecutor.call("list_sessions")
print(result)

# 关闭 session
ToolExecutor.call("close_session my_session")
```

## Session 特性

### 1. 独立工作目录

每个 session 维护自己独立的工作目录：

```python
# 创建两个 session
ToolExecutor.call("create_session s1")
ToolExecutor.call("create_session s2")

# s1 切换到 /tmp
ToolExecutor.call("session_exec s1 cd /tmp")

# s2 保持在原目录
result = ToolExecutor.call("session_exec s1 pwd")
# 输出：/tmp

result = ToolExecutor.call("session_exec s2 pwd")
# 输出：/Users/xxx/project (原目录)

# 查看 session 列表（显示不同 cwd）
result = ToolExecutor.call("list_sessions")
# 输出:
# 活跃 session 列表:
#   s1 [活跃] cwd: /tmp
#   s2 [活跃] cwd: /Users/xxx/project
```

### 2. 环境变量隔离

每个 session 有独立的环境变量：

```python
# session1 设置变量
ToolExecutor.call("session_exec s1 export API_KEY=secret123")
ToolExecutor.call("session_exec s1 echo $API_KEY")
# 输出：secret123

# session2 不受影响
ToolExecutor.call("session_exec s2 echo $API_KEY")
# 输出：(空)
```

### 3. 管道和重定向

支持完整的 bash 语法：

```python
# 管道
ToolExecutor.call("session_exec s1 'ls -la | grep .py'")

# 重定向
ToolExecutor.call("session_exec s1 'echo hello > output.txt'")

# 多命令
ToolExecutor.call("session_exec s1 'cd /app && ls -la'")
```

## LLM 调用示例

LLM 可以这样调用 session：

```json
{
    "command": "create_session audit_1",
    "logic": "创建一个新的 session 用于代码审计"
}
```

```json
{
    "command": "session_exec audit_1 cd /app/src",
    "logic": "切换到源代码目录"
}
```

```json
{
    "command": "session_exec audit_1 python -c \"import sys; print(sys.version)\"",
    "logic": "检查 Python 版本"
}
```

```json
{
    "command": "list_sessions",
    "logic": "查看当前有哪些活跃的 session"
}
```

```json
{
    "command": "close_session audit_1",
    "logic": "审计完成，清理 session"
}
```

## 注意事项

1. **Session 命名**：建议使用有意义的名称，如 `build_session`、`audit_1` 等
2. **及时清理**：使用完毕后调用 `close_session` 释放资源
3. **命令格式**：复杂命令（含管道、重定向）建议用单引号包裹
4. **超时设置**：长时间运行的命令可能超时（默认 30 秒）

## 典型使用场景

### 场景 1：构建和测试

```python
# 创建构建 session
ToolExecutor.call("create_session build")

# 安装依赖
ToolExecutor.call("session_exec build pip install -r requirements.txt")

# 运行测试
ToolExecutor.call("session_exec build pytest tests/")

# 构建
ToolExecutor.call("session_exec build python setup.py build")

# 清理
ToolExecutor.call("close_session build")
```

### 场景 2：代码审计

```python
# 创建审计 session
ToolExecutor.call("create_session audit")

# 切换到目标目录
ToolExecutor.call("session_exec audit cd /app/vulnerable_code")

# 查看文件结构
ToolExecutor.call("session_exec audit find . -name '*.py'")

# 搜索危险函数
ToolExecutor.call("session_exec audit 'grep -r \"eval(\" . '")
ToolExecutor.call("session_exec audit 'grep -r \"os.system(\" . '")

# 清理
ToolExecutor.call("close_session audit")
```
