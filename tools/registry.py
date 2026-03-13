class ToolRegistry:
    """工具注册中心"""

    # 命令名 -> Tool 类
    _commands: dict[str, type] = {}
    # Tool 类列表（用 name 作为 key）
    _tools: dict[str, type] = {}

    @classmethod
    def register(cls, tool_class: type) -> type:
        """注册一个工具类，自动注册其所有命令"""
        if not hasattr(tool_class, "name"):
            raise ValueError("Tool class must have 'name' attribute")
        if not hasattr(tool_class, "commands"):
            raise ValueError("Tool class must have 'commands' attribute")

        # 注册该类的所有命令
        for command_name in tool_class.commands.keys():
            cls._commands[command_name] = tool_class

        cls._tools[tool_class.name] = tool_class
        return tool_class

    @classmethod
    def get_tool_for_command(cls, command: str) -> type | None:
        """获取处理指定命令的 Tool 类"""
        return cls._commands.get(command)

    @classmethod
    def get_all_commands(cls) -> list[str]:
        """获取所有已注册的命令"""
        return list(cls._commands.keys())

    @classmethod
    def get_tools_by_names(cls, names: list[str]) -> list[type]:
        """根据名称获取指定的 Tool 类"""
        return [t for t in cls._tools.values() if t.name in names]

    @classmethod
    def check_availability(cls) -> dict[str, str]:
        """检查所有工具的可用性，返回 {tool_name: status}"""
        results = {}
        for tool_name, tool_class in cls._tools.items():
            if hasattr(tool_class, 'check_availability'):
                status = tool_class.check_availability()
            else:
                status = "可用"
            results[tool_name] = status
        return results

    @classmethod
    def to_openai_tools(cls, tool_names: list[str] | None = None) -> list[dict]:
        """
        生成 OpenAI tools schema

        Args:
            tool_names: 指定要包含的命令列表，None 表示全部

        Returns:
            OpenAI tools 格式的列表
        """
        if tool_names is None:
            tool_names = cls.get_all_commands()

        tools = []
        for command in tool_names:
            tool_class = cls._commands.get(command)
            if tool_class is None:
                continue

            cmd_info = tool_class.commands.get(command)
            if cmd_info is None:
                continue

            # 使用命令定义中的 parameters，如果没有则使用空 schema
            parameters = cmd_info.get("parameters", {
                "type": "object",
                "properties": {},
            })

            tools.append({
                "type": "function",
                "function": {
                    "name": command,
                    "description": cmd_info.get("description", ""),
                    "parameters": parameters,
                }
            })

        return tools