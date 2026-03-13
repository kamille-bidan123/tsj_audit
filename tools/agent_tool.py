#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Tool - 启动子 Agent 的工具

工具定义，用于生成 OpenAI tools schema。
实际执行由 trace_agent 直接调用相应的 sub-agent 完成。
"""

from tools.registry import ToolRegistry


@ToolRegistry.register
class AgentTool:
    """启动子 Agent 的工具"""

    name = "audit"
    description = "启动子 Agent 进行漏洞审计"

    commands = {
        "audit": {
            "description": "启动漏洞审计 Agent，根据审计类型分析代码中是否存在相应的安全漏洞",
            "parameters": {
                "type": "object",
                "properties": {
                    "audit_type": {
                        "type": "string",
                        "enum": ["command_injection", "path_traversal"],
                        "description": "审计类型：command_injection（命令注入）或 path_traversal（路径遍历）",
                    },
                },
                "required": [],
            },
        },
    }

    def execute(self, command: str, args: dict) -> str:
        """执行命令（不会被调用，由 trace_agent 直接处理）"""
        return "此工具由 trace_agent 直接处理"