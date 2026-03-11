# Tools 模块
# 自动导入所有工具以完成注册

from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.prompt_generator import ToolPromptGenerator

# 导入所有工具模块以完成注册
from tools.file_tool import FileTool
from tools.shell_tool import ShellTool
from tools.tags_tool import TagsTool

__all__ = [
    "ToolRegistry",
    "ToolExecutor",
    "ToolPromptGenerator",
    "FileTool",
    "ShellTool",
    "TagsTool",
]