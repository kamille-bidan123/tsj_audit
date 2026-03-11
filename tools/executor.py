from tools.registry import ToolRegistry


class ToolExecutor:
    """工具执行器，解析并执行命令"""

    @classmethod
    def call(cls, command_str: str) -> str:
        """
        执行命令字符串

        Args:
            command_str: 完整命令，如 "read_file open.c:1-5"

        Returns:
            执行结果
        """
        parts = command_str.strip().split(" ", 1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        tool_class = ToolRegistry.get_tool_for_command(command)
        if tool_class is None:
            return f"错误：未知命令 '{command}'"

        tool = tool_class()
        return tool.execute(command, args)