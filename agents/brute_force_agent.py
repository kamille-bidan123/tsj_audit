#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BruteForceAgent - Web 防暴力破解漏洞审计 Agent

检查密码校验接口是否有防暴力破解机制
"""

import sys
import json
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from models import CodeContext, AuditResult, FunctionInfo
from utils.llm_client import LLMClient
from cli import get_config_object
# 导入提示词
from agents.prompt import (
    build_brute_force_system_prompt,
    build_brute_force_user_message,
)


class BruteForceSubmitTool:
    """提交暴力破解审计结果的工具"""

    name = "submit_brute_force"
    description = "提交暴力破解审计结果"

    commands = {
        "submit_brute_force": {
            "description": "暴力破解审计完成，提交审计结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "审计发现的总结",
                    },
                    "is_vulnerable": {
                        "type": "boolean",
                        "description": "是否存在暴力破解漏洞",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "漏洞置信度",
                    },
                    "description": {
                        "type": "string",
                        "description": "漏洞描述",
                    },
                    "taint_flow": {
                        "type": "string",
                        "description": "污点流向描述",
                    },
                    "recommendation": {
                        "type": "string",
                        "description": "修复建议",
                    },
                    "code_map": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "function_name": {"type": "string"},
                                "file_path": {"type": "string"},
                                "line_start": {"type": "integer"},
                                "line_end": {"type": "integer"},
                                "code_snippet": {"type": "string"},
                                "is_entry_point": {"type": "boolean"},
                                "taint_source": {"type": "string"},
                                "taint_path": {"type": "string"},
                            },
                        },
                        "description": "相关代码上下文列表",
                    },
                },
                "required": ["is_vulnerable", "confidence"],
            },
        },
    }

    def execute(self, command: str, args: dict) -> str:
        return "已提交暴力破解审计结果"


# 注册 submit_brute_force 工具
ToolRegistry._commands["submit_brute_force"] = BruteForceSubmitTool
ToolRegistry._tools["submit_brute_force"] = BruteForceSubmitTool


class BruteForceAgent:
    """
    Web 防暴力破解漏洞审计 Agent

    检查密码校验接口是否有防暴力破解机制
    """

    EXPLORATION_TOOLS = [
        "read_file", "list_dir", "search_code",
        "go_to_def", "find_refs",
        "skill",  # Skills 工具
        "submit_brute_force",
    ]

    # 密码相关关键词
    PASSWORD_KEYWORDS = [
        "password", "passwd", "pwd", "pin", "verify_password",
        "check_password", "auth_password", "login_password",
        "confirm_password", "validate_password", "password_verify",
    ]

    # 暴力破解防护机制关键词
    PROTECTION_KEYWORDS = [
        "lock", "ban", "block", "limit", "retry", "attempt",
        "timeout", "cooldown", "wait", "interval",
        "failed_count", "failed_times", "failed_num",
        "max_retry", "max_attempt", "max_failed",
        "captcha", "verify_code", "security_code",
    ]

    def __init__(
        self,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
    ):
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

        self._llm_client = None
        self._tools_schema: Optional[List[Dict]] = None

    @property
    def llm_client(self):
        """懒加载 LLM 客户端"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    @property
    def tools_schema(self) -> List[Dict]:
        """获取 OpenAI tools schema"""
        if self._tools_schema is None:
            self._tools_schema = ToolRegistry.to_openai_tools(self.EXPLORATION_TOOLS)
        return self._tools_schema

    def call_tool(self, name: str, arguments: Dict) -> str:
        """调用工具执行"""
        result = ToolExecutor.call(name, arguments)
        if self.debug:
            print(f"  [Tool] {name}({arguments}) -> {result[:100]}...", file=sys.stderr)
        return result

    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        return build_brute_force_system_prompt(self.function_info.func_name)

    def _build_user_message(self) -> str:
        """构建用户消息，包含 codemap"""
        code_map_str = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False
        )
        return build_brute_force_user_message(code_map_str)

    def _save_conversation_history(self, messages: List[Dict]):
        """保存该 agent 的对话历史"""
        if not self.output_dir:
            return  # 如果没有设置输出目录，则不保存

        # 构建输出目录结构：output_dir/conversations/agent_name/function_name.json
        conversations_dir = Path(self.output_dir) / "conversations" / "brute_force_agent"
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # 清理函数名中的非法字符
        safe_func_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in self.function_info.func_name)

        conversation_file = conversations_dir / f"{safe_func_name}.json"

        # 准备保存对话历史
        conversation_data = {
            "function_info": self.function_info.model_dump(),
            "conversation_history": messages,
            "saved_at": datetime.now().isoformat(),
            "agent": "brute_force_agent"
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [对话历史] brute_force_agent 已保存: {conversation_file}", file=sys.stderr)

    def audit(self) -> AuditResult:
        """
        执行审计

        Returns:
            AuditResult 审计结果
        """
        # 构建消息
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if self.debug:
            print(f"\n[BruteForceAgent] 开始审计", file=sys.stderr)

        max_turns = get_config_object().max_turns
        for turn in range(max_turns):
            if self.debug:
                print(f"\n[第{turn+1}轮]", file=sys.stderr)

            response = self.llm_client.chat(
                messages=messages,
                tools=self.tools_schema,
                tool_choice="required",
                temperature=0.1,
            )

            # 检查是否有工具调用
            if response.tool_calls:
                for tc in response.tool_calls:
                    print(f"\n[工具调用] {tc['function']['name']}({tc['function']['arguments']})", file=sys.stderr)
                    func_name = tc["function"]["name"]
                    arguments = tc["function"]["arguments"]

                    # 检查是否是 submit_brute_force 调用
                    if func_name == "submit_brute_force":
                        print("[提交审计结果]", file=sys.stderr)
                        # 保存对话历史
                        self._save_conversation_history(messages)
                        return self._parse_audit_result(arguments, messages)

                    # 特殊处理，禁止直接search_code搜索关键词
                    if func_name == "search_code" and "pattern" in arguments:
                        pattern = arguments["pattern"]
                        if pattern in self.PASSWORD_KEYWORDS or pattern in self.PROTECTION_KEYWORDS:
                            print(f"  [警告] 禁止直接搜索关键词 '{pattern}'，请通过分析数据流来发现潜在的暴力破解漏洞", file=sys.stderr)
                            result = f"错误：禁止直接搜索关键词 '{pattern}'，请通过分析数据流来发现潜在的暴力破解漏洞"
                        else:
                            result = self.call_tool(func_name, arguments)
                    # 执行工具
                    else:
                        result = self.call_tool(func_name, arguments)

                    # 将工具结果添加到对话
                    tc_for_message = {
                        "id": tc["id"],
                        "type": tc["type"],
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False),
                        }
                    }
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tc_for_message],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
            else:
                # 没有工具调用，提示 LLM 使用工具
                if self.debug:
                    print("[提示] 请使用工具进行审计，或调用 submit 结束", file=sys.stderr)
                messages.append({
                    "role": "user",
                    "content": "请使用工具进行审计，或调用 submit_brute_force 工具结束审计。"
                })

        # 达到最大轮数，返回空结果，但仍保存对话历史
        self._save_conversation_history(messages)
        return AuditResult(
            vulnerability_type="brute_force",
            is_vulnerable=False,
            confidence="low",
            description="审计未完成",
            code_map=self.code_map,
        )

    def _parse_audit_result(self, submit_args: dict, messages: List[Dict]) -> AuditResult:
        """解析审计结果"""
        # 处理 code_map
        code_map_data = submit_args.get("code_map", [])
        code_map = []
        for cm in code_map_data:
            code_map.append(CodeContext(
                function_name=cm.get("function_name", ""),
                file_path=cm.get("file_path", ""),
                line_start=cm.get("line_start", 0),
                line_end=cm.get("line_end", 0),
                code_snippet=cm.get("code_snippet", ""),
                is_entry_point=cm.get("is_entry_point", False),
                taint_source=cm.get("taint_source"),
                taint_path=cm.get("taint_path"),
            ))

        print(f"\n[审计结果] is_vulnerable={submit_args.get('is_vulnerable')}, confidence={submit_args.get('confidence')}", file=sys.stderr)
        return AuditResult(
            vulnerability_type="brute_force",
            is_vulnerable=submit_args.get("is_vulnerable", False),
            confidence=submit_args.get("confidence", "low"),
            description=submit_args.get("description") or submit_args.get("summary", ""),
            taint_flow=submit_args.get("taint_flow"),
            recommendation=submit_args.get("recommendation"),
            code_map=code_map,
        )
