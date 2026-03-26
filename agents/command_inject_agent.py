#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CommandInjectAgent - 命令注入漏洞审计 Agent

基于 codemap 进行命令注入漏洞的深度审计
"""

import os
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


class CommandInjectSubmitTool:
    """提交命令注入审计结果的工具"""

    name = "submit_command_inject"
    description = "提交命令注入审计结果"

    commands = {
        "submit_command_inject": {
            "description": "命令注入审计完成，提交审计结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "审计发现的总结",
                    },
                },
                "required": ["summary"],
            },
        },
    }

    def execute(self, command: str, args: dict) -> str:
        return "已提交命令注入审计结果"


# 注册 submit_command_inject 工具
ToolRegistry._commands["submit_command_inject"] = CommandInjectSubmitTool
ToolRegistry._tools["submit_command_inject"] = CommandInjectSubmitTool


class CommandInjectAgent:
    """
    命令注入漏洞审计 Agent

    基于 codemap 进行深度审计，识别命令注入漏洞
    """

    EXPLORATION_TOOLS = [
        "read_file", "list_dir", "search_code",
        "go_to_def", "find_refs",
        "skill",  # Skills 工具
        "submit_command_inject",
    ]

    # 危险函数列表
    DANGEROUS_FUNCTIONS = [
        "system", "popen", "execve", "execl", "execlp", "execle", "execv", "execvp", "execvpe",
        "spawn", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
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

        return f"""你是一个代码安全审计专家，专门进行命令注入漏洞审计。

## 任务
从接口函数 {self.function_info.func_name} 开始
基于提供的 codemap，深入分析代码中是否存在命令注入漏洞。

## 危险函数
命令注入相关的危险函数包括：
{', '.join(self.DANGEROUS_FUNCTIONS)}

## 审计要点
1. 检查外部输入是否直接或间接传递给危险函数
2. 分析数据流：外部输入 -> 中间变量 -> 危险函数
3. 检查是否有有效的输入验证/过滤
4. 评估漏洞的可利用性

## 工具使用
你可以使用提供的工具来探索代码。每次调用一个工具，根据结果决定下一步行动。
工具的详细说明（包括参数和使用场景）已在工具 schema 中定义，请参考工具描述。

## 输出格式
当你认为已经审计完成时，调用 submit_command_inject 工具提交审计结果。

强制要求：
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注上面提供的接口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
重要的事情说三遍
"""

    def _build_user_message(self) -> str:
        """构建用户消息，包含 codemap"""
        code_map_str = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False
        )

        return f"""请基于以下 codemap 进行命令注入漏洞审计：

```json
{code_map_str}
```

请使用工具调用来深入分析代码，确认是否存在命令注入漏洞。
当你认为已经审计完成时，调用 submit_command_inject 工具提交审计结果。
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
            print(f"\n[CommandInjectAgent] 开始审计", file=sys.stderr)
        max_turns = get_config_object().max_turns
        for turn in range(max_turns):  # 使用固定的轮数
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

                    # 检查是否是 submit_command_inject 调用
                    if func_name == "submit_command_inject":
                        print("[提交审计结果]", file=sys.stderr)
                        # 保存对话历史
                        self._save_conversation_history(messages)
                        # 解析审计结果
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
                    print("[提示] 请使用工具进行审计，或调用 submit_command_inject 结束", file=sys.stderr)
                messages.append({
                    "role": "user",
                    "content": "请使用工具进行审计，或调用 submit_command_inject 工具结束审计。"
                })

        # 达到最大轮数，返回空结果
        return AuditResult(
            vulnerability_type="command_injection",
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
            "content": f"""请输出结构化的审计结果（JSON格式）,你应该只输出接口函数{self.function_info.func_name}是否有命令注入的判断结果：
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
            vulnerability_type="command_injection",
            is_vulnerable=data.get("is_vulnerable", False),
            confidence=data.get("confidence", "low"),
            description=data.get("description", summary),
            taint_flow=data.get("taint_flow"),
            recommendation=data.get("recommendation"),
            code_map=self.code_map,
        )

    def _save_conversation_history(self, messages: List[Dict]):
        """保存该 agent 的对话历史"""
        if not self.output_dir:
            return  # 如果没有设置输出目录，则不保存

        # 构建输出目录结构：output_dir/conversations/agent_name/function_name.json
        conversations_dir = Path(self.output_dir) / "conversations" / "command_inject_agent"
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # 清理函数名中的非法字符
        safe_func_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in self.function_info.func_name)

        conversation_file = conversations_dir / f"{safe_func_name}.json"

        # 准备保存对话历史
        conversation_data = {
            "function_info": self.function_info.model_dump(),
            "conversation_history": messages,
            "saved_at": datetime.now().isoformat(),
            "agent": "command_inject_agent"
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [对话历史] command_inject_agent 已保存: {conversation_file}", file=sys.stderr)

