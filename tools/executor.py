from tools.registry import ToolRegistry


class ToolExecutor:
    """工具执行器，接收 OpenAI function calling 格式的参数"""

    @classmethod
    def call(cls, function_name: str, arguments: dict) -> str:
        """
        执行工具调用

        Args:
            function_name: 函数名/命令名，如 "read_file"
            arguments: 参数字典，如 {"path": "main.c", "start": 1, "end": 20}

        Returns:
            执行结果
        """
        print(f'tool call:\nfunction_name:{function_name}\nargs:{arguments}')
        tool_class = ToolRegistry.get_tool_for_command(function_name)
        if tool_class is None:
            return f"错误：未知命令 '{function_name}'"

        tool = tool_class()
        ret = tool.execute(function_name, arguments)
        print('command ret:\n'+ret)
        return ret
