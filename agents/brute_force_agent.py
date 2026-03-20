#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BruteForceAgent - Web 防暴力破解漏洞审计 Agent

检查密码校验接口是否有防暴力破解机制
"""

import sys
import json
from typing import List, Dict, Optional

from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from models import CodeContext, AuditResult, FunctionInfo
from utils.llm_client import LLMClient
from cli import get_config_object


class BruteForceAgent:
    """
    Web 防暴力破解漏洞审计 Agent

    检查密码校验接口是否有防暴力破解机制
    """

    EXPLORATION_TOOLS = [
        "read_file", "list_dir", "search_code",
        "go_to_def", "find_refs",
        "skill",  # Skills 工具
        "submit",
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
    ):
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug

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
        return f"""你是一个代码安全审计专家，专门进行 Web 防暴力破解漏洞审计。

## 任务
从接口函数 {self.function_info.func_name} 开始
基于提供的 codemap，分析代码中是否存在暴力破解漏洞。

## 漏洞定义
当外部输入（如密码）在校验时，如果没有防暴力破解机制，则存在漏洞。
暴力破解漏洞指：攻击者可以无限次尝试密码，直到猜对为止。

## 审计要点
1. 检查密码校验函数中是否存在暴力破解防护机制
2. 防护机制包括但不限于：
   - 失败次数限制（如 3 次失败后锁定）
   - 时间间隔限制（如失败后等待 30 分钟）
   - 验证码机制
   - IP 封禁机制
   - 登录频率限制
3. 分析数据流：外部输入 -> 密码校验 -> 防护机制检查
4. 如果存在防护机制，检查其实现是否有效
5. 如果外部输入根本就没有密码，直接输出没有问题

## 漏洞判断标准
- 存在密码相关输入但没有任何防护机制 -> 高置信度漏洞
- 仅有失败次数限制但没有时间限制 -> 中置信度漏洞
- 仅有时间限制但没有失败次数限制 -> 中置信度漏洞
- 同时存在次数和时间限制 -> 低风险或无漏洞

## 工具使用
你可以使用提供的工具来探索代码。每次调用一个工具，根据结果决定下一步行动。
工具的详细说明（包括参数和使用场景）已在工具 schema 中定义，请参考工具描述。

## 输出格式
当你认为已经审计完成时，调用 submit 工具提交审计结果。

强制要求：
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
"""

    def _build_user_message(self) -> str:
        """构建用户消息，包含 codemap"""
        code_map_str = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False
        )

        return f"""请基于以下 codemap 进行防暴力破解漏洞审计：

```json
{code_map_str}
```

请使用工具调用来深入分析代码，确认密码校验接口是否有防暴力破解机制。
当你认为已经审计完成时，调用 submit 工具提交审计结果。
"""

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

                    # 检查是否是 submit 调用
                    if func_name == "submit":
                        print("[提交审计结果]", file=sys.stderr)
                        return self._parse_audit_result(arguments, messages)

                    # 执行工具
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
                    "content": "请使用工具进行审计，或调用 submit 工具结束审计。"
                })

        # 达到最大轮数，返回空结果
        return AuditResult(
            vulnerability_type="brute_force",
            is_vulnerable=False,
            confidence="low",
            description="审计未完成",
            code_map=self.code_map,
        )

    def _parse_audit_result(self, submit_args: dict, messages: List[Dict]) -> AuditResult:
        """解析审计结果"""
        summary = submit_args.get("summary", "")

        # 让 LLM 输出结构化的审计结果
        messages.append({
            "role": "user",
            "content": """请输出结构化的审计结果（JSON格式）：
{
  "is_vulnerable": true/false,
  "confidence": "high"/"medium"/"low",
  "description": "漏洞描述",
  "taint_flow": "污点流向描述",
  "recommendation": "修复建议"
}"""
        })

        response = self.llm_client.chat(
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        try:
            from utils.llm_client import extract_json
            json_str = extract_json(response.content)
            if json_str:
                data = json.loads(json_str)
            else:
                data = {}
        except json.JSONDecodeError:
            data = {}

        print(f"\n[审计结果] {data}", file=sys.stderr)

        return AuditResult(
            vulnerability_type="brute_force",
            is_vulnerable=data.get("is_vulnerable", False),
            confidence=data.get("confidence", "low"),
            description=data.get("description", summary),
            taint_flow=data.get("taint_flow"),
            recommendation=data.get("recommendation"),
            code_map=self.code_map,
        )
