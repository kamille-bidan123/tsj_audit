from tools.registry import ToolRegistry


class ToolPromptGenerator:
    """生成工具调用的提示词"""

    @classmethod
    def generate(cls, tool_names: list[str] | None = None) -> str:
        """
        生成工具调用的完整 prompt

        Args:
            tool_names: 指定要包含的工具命令列表，None 表示全部

        Returns:
            生成的 prompt 字符串
        """
        if tool_names is None:
            tool_names = ToolRegistry.get_all_commands()

        prompt = "## 可用工具\n\n"
        prompt += "你可以使用以下工具来完成代码审计任务。\n"
        prompt += "每个工具都通过命令行形式调用。\n\n"

        # 按工具类分组显示
        processed_tools = set()
        for command in tool_names:
            tool_class = ToolRegistry.get_tool_for_command(command)
            if tool_class is None:
                continue
            if tool_class in processed_tools:
                continue
            processed_tools.add(tool_class)

            prompt += f"**{tool_class.name}** - {tool_class.description}\n\n"

            for cmd in tool_class.commands.keys():
                prompt += ToolRegistry.to_prompt(cmd) + "\n"

        prompt += "---\n\n"
        prompt += "## 调用格式\n\n"
        prompt += "当你需要调用工具时，请返回以下 JSON 格式：\n\n"
        prompt += """```json
{
    "command": "<tool_name> <args>",
    "logic": "说明为什么调用这个工具"
}
```

"""
        prompt += "### 字段说明\n\n"
        prompt += "- **command**: 完整的命令行字符串，包括工具名和参数\n"
        prompt += "- **logic**: 说明调用这个工具的原因和目的\n\n"
        prompt += "### 示例\n\n"
        prompt += """```json
{
    "command": "read_file open.c:1-20",
    "logic": "查看 open.c 文件的前 20 行，了解文件打开的逻辑"
}
```

"""
        prompt += """```json
{
    "command": "search_code vuln",
    "logic": "搜索代码中包含 'vuln' 的地方，查找潜在漏洞"
}
```
"""

        return prompt
