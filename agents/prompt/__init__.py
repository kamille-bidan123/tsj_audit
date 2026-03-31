# Prompt 目录初始化文件
# 导出所有 prompt 构建函数

from agents.prompt.trace_prompt import (
    EXPLORATION_SYSTEM_PROMPT,
    build_exploration_user_message,
)

from agents.prompt.trace_tool_guide import (
    TRACE_TOOL_GUIDE,
    get_trace_tool_guide,
)

from agents.prompt.command_inject_prompt import (
    DANGEROUS_FUNCTIONS as COMMAND_INJECT_DANGEROUS_FUNCTIONS,
    build_system_prompt as build_command_inject_system_prompt,
    build_user_message as build_command_inject_user_message,
)

from agents.prompt.path_traversal_prompt import (
    DANGEROUS_FUNCTIONS as PATH_TRAVERSAL_DANGEROUS_FUNCTIONS,
    build_system_prompt as build_path_traversal_system_prompt,
    build_user_message as build_path_traversal_user_message,
)

from agents.prompt.brute_force_prompt import (
    build_system_prompt as build_brute_force_system_prompt,
    build_user_message as build_brute_force_user_message,
)

__all__ = [
    # Trace
    "EXPLORATION_SYSTEM_PROMPT",
    "build_exploration_user_message",
    "TRACE_TOOL_GUIDE",
    "get_trace_tool_guide",
    # Command Inject
    "COMMAND_INJECT_DANGEROUS_FUNCTIONS",
    "build_command_inject_system_prompt",
    "build_command_inject_user_message",
    # Path Traversal
    "PATH_TRAVERSAL_DANGEROUS_FUNCTIONS",
    "build_path_traversal_system_prompt",
    "build_path_traversal_user_message",
    # Brute Force
    "build_brute_force_system_prompt",
    "build_brute_force_user_message",
]