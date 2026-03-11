# -*- coding: utf-8 -*-
from agents.base import Agent


class CodeAuditAgent(Agent):
    """代码审计 Agent，使用文件工具和 shell 工具"""

    name = "code_audit_agent"
    description = "用于代码审计的 Agent"

    # 选择需要的工具命令
    TOOLS = [
        # 文件操作
        "read_file",
        "list_dir",
        "search_code",
        # Shell 命令和 session 管理
        "run_command",
        "create_session",
        "session_exec",
        "close_session",
        "list_sessions",
        # 代码导航
        "go_to_def",
        "find_refs",
        "list_symbols",
    ]


class SimpleAgent(Agent):
    """简单 Agent，只使用基本工具"""

    name = "simple_agent"
    description = "只读操作的简单 Agent"

    # 只允许读取文件
    TOOLS = [
        "read_file",
        "list_dir",
    ]
