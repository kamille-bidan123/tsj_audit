# -*- coding: utf-8 -*-
from tools.executor import ToolExecutor
from tools.prompt_generator import ToolPromptGenerator
from tools.registry import ToolRegistry


class Agent:
    """Agent 基类，支持选择需要的工具"""

    name: str = "agent"
    description: str = ""

    # Agent 选择自己需要的工具命令列表
    TOOLS: list[str] = []

    def __init__(self):
        self.tools = self.TOOLS

    def get_system_prompt(self) -> str:
        """获取 system prompt，包含工具说明"""
        return ToolPromptGenerator.generate(self.tools)

    def execute_tool(self, command: str) -> str:
        """
        执行工具命令

        Args:
            command: 完整命令字符串，如 "read_file main.py:1-10"

        Returns:
            执行结果
        """
        # 检查是否是允许的工具
        parts = command.strip().split(" ", 1)
        tool_name = parts[0]

        if self.TOOLS and tool_name not in self.TOOLS:
            return f"错误：'{tool_name}' 不在此 Agent 允许的工具列表中"

        return ToolExecutor.call(command)

    def handle_llm_response(self, response: dict) -> str:
        """
        处理 LLM 返回的工具调用请求

        Args:
            response: {"command": "...", "logic": "..."}

        Returns:
            执行结果
        """
        command = response.get("command")
        logic = response.get("logic", "")

        print(f"[Agent] 执行工具：{command}")
        print(f"[Agent] 原因：{logic}")

        result = self.execute_tool(command)

        print(f"[Agent] 结果：{result[:100]}..." if len(result) > 100 else f"[Agent] 结果：{result}")
        return result
