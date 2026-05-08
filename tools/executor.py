from tools.registry import ToolRegistry
from utils.tool_call_guard import ToolCallGuard
from utils.tool_call_logger import ToolCallLogger


class ToolExecutor:
    """工具执行器，接收 OpenAI function calling 格式的参数"""

    @classmethod
    def call(
        cls,
        function_name: str,
        arguments: dict,
        *,
        audit_function_name: str | None = None,
        tool_guard: ToolCallGuard | None = None,
    ) -> str:
        """
        执行工具调用

        Args:
            function_name: 函数名/命令名，如 "read_file"
            arguments: 参数字典，如 {"path": "main.c", "start": 1, "end": 20}

        Returns:
            执行结果
        """
        debug = cls._is_debug_enabled()
        call_id = ToolCallLogger.start(
            function_name,
            arguments,
            audit_function_name=audit_function_name,
            debug=debug,
        )
        guard_error = tool_guard.check(function_name, arguments) if tool_guard else None
        if guard_error is not None:
            ToolCallLogger.end(
                call_id,
                function_name,
                guard_error,
                audit_function_name=audit_function_name,
                debug=debug,
            )
            return guard_error

        tool_class = ToolRegistry.get_tool_for_command(function_name)
        if tool_class is None:
            ret = f"错误：未知命令 '{function_name}'"
            ToolCallLogger.end(
                call_id,
                function_name,
                ret,
                audit_function_name=audit_function_name,
                debug=debug,
            )
            return ret

        tool = tool_class()
        try:
            ret = tool.execute(function_name, arguments)
        except Exception as exc:
            ToolCallLogger.error(
                call_id,
                function_name,
                exc,
                audit_function_name=audit_function_name,
                debug=debug,
            )
            raise

        ToolCallLogger.end(
            call_id,
            function_name,
            ret,
            audit_function_name=audit_function_name,
            debug=debug,
        )
        return ret

    @staticmethod
    def _is_debug_enabled() -> bool:
        try:
            from config import get_config

            return bool(get_config().debug)
        except Exception:
            return False
