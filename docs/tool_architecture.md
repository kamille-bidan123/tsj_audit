# Tool Call 架构说明

## 初始化时机

### Tool 类的 `__init__` / `initialize()`

工具类采用**单例模式**，`__init__` 在**首次执行命令时**自动调用，且只执行一次。

```python
from tools.base import Tool
from tools.registry import ToolRegistry

class MyTool(Tool):
    name = "my_tool"
    description = "我的工具"

    commands = {
        "do_something": {"description": "...", "usage": "...", "examples": []},
    }

    def initialize(self):
        """延迟初始化钩子，只执行一次

        适合用于：
        - 加载配置
        - 建立数据库连接
        - 创建临时目录
        - 读取环境变量
        """
        self.config = load_config()
        self.db = connect_db()

    def execute(self, command: str, args: str) -> str:
        # ...
        pass

ToolRegistry.register(MyTool)
```

### 初始化顺序

```
1. 导入工具模块 → 调用 ToolRegistry.register()
2. 首次执行命令 → ToolExecutor.call("my_command ...")
3. 创建工具实例 → tool = MyTool()
4. 自动调用 __init__ → 检查 _initialized
5. 自动调用 initialize() → 执行子类初始化逻辑
6. 设置 _initialized = True
7. 执行 execute()
```

### 全局配置注入

```python
from tools.executor import ToolExecutor



# 工具类中读取配置
class FileTool(Tool):
    def initialize(self):
        # 从 ToolExecutor 获取配置
        config = ToolExecutor.get_config()
        self.workdir = config.get("workdir", "./")
```

### 重新初始化

如果需要重新初始化，调用：

```python
# 手动重置
from tools.file_tool import FileTool
FileTool.reset_instance()

# 下次执行时会重新调用 initialize()
ToolExecutor.call("read_file test.txt")
```

## 本地模式（默认）

```python
# LLM 命令
{"command": "read_file src/main.c:1-10"}

# 直接读取本地文件
cat src/main.c | head -n 10
```

## 添加新工具

```python
# 1. 创建工具类
from tools.base import Tool
from tools.registry import ToolRegistry

class NewTool(Tool):
    name = "new_tool"
    description = "新工具"

    commands = {
        "cmd1": {"description": "...", "usage": "...", "examples": []},
    }

    def initialize(self):
        # 初始化逻辑
        pass

    def execute(self, command: str, args: str) -> str:
        if command == "cmd1":
            return self._cmd1(args)

    def _cmd1(self, args: str) -> str:
        # 实现逻辑
        return "result"

# 2. 注册（在 tools/__init__.py 中导入即可）
ToolRegistry.register(NewTool)
```

## 最佳实践

1. **不要在 `__init__` 中写逻辑** - 使用 `initialize()` 钩子
2. **工具类无状态** - 每次执行都是新的上下文，不要依赖实例变量
3. **错误处理** - 所有错误返回字符串，不要抛异常
4. **超时控制** - 外部命令设置 timeout，避免卡死
5. **路径安全** - 拼接路径前检查是否越界