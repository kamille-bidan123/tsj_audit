#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 客户端模块

薄封装 OpenAI API，配置通过 config 模块获取。
"""

import sys
import json
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


def extract_json(response: str, is_array: bool = False) -> Optional[str]:
    """从 LLM 响应中提取 JSON 字符串"""
    # 移除思考标签
    response = re.sub(r'ètes[\s\S]*?êtes', '', response)
    response = re.sub(r'[\s\S]*?êtes', '', response)

    # 优先从 ```json 代码块提取
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, response, re.DOTALL)
    if matches:
        return matches[0].strip()

    # 直接匹配 JSON 对象或数组
    pattern = r'\[[\s\S]*\]' if is_array else r'\{[\s\S]*\}'
    json_match = re.search(pattern, response)
    if json_match:
        return json_match.group(0)

    return None


@dataclass
class ChatResponse:
    """聊天响应"""
    content: str = ""
    reasoning_content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None


class LLMClient:
    """
    LLM 客户端，薄封装 OpenAI API

    只负责：
    1. 获取配置
    2. 创建 client
    3. 处理响应（debug 模式用流式，非 debug 模式用非流式）
    """

    def chat(self, **kwargs) -> ChatResponse:
        """
        发送聊天请求

        Args:
            **kwargs: 直接传递给 OpenAI API 的参数
                - messages: 消息列表
                - tools: 工具列表（可选）
                - tool_choice: 工具选择策略（可选）
                - response_format: 响应格式（可选）
                - temperature: 温度参数（可选）
                - max_tokens: 最大 token 数（可选）

        Returns:
            ChatResponse 响应对象
        """
        from config import get_config
        config = get_config()

        from openai import OpenAI
        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

        # 添加必要参数
        kwargs["model"] = kwargs.get("model", config.model_name)
        if config.model_name.startswith("deepseek-r1"):
            kwargs.pop('temperature', None)

        debug = config.debug

        # debug 模式使用流式，非 debug 模式使用非流式
        if debug:
            return self._chat_stream(client, kwargs)
        else:
            return self._chat_non_stream(client, kwargs)

    def _chat_stream(self, client, kwargs: Dict) -> ChatResponse:
        """流式输出（debug 模式）"""
        kwargs["stream"] = True

        try:
            stream = client.chat.completions.create(**kwargs)

            full_content = ""
            reasoning_content = ""
            tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
            first_content = True
            first_reasoning = True

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # 正文内容
                content = getattr(delta, 'content', None)
                if content:
                    full_content += content
                    if first_content:
                        print("\n📝:", file=sys.stdout, flush=True)
                        first_content = False
                    print(content, end="", file=sys.stdout, flush=True)

                # 工具调用
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or "",
                                "type": tc.type or "function",
                                "function": {
                                    "name": "",
                                    "arguments": "",
                                }
                            }
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

                # 推理内容
                reasoning = getattr(delta, 'reasoning', None) or getattr(delta, 'thought', None) or getattr(delta, 'reasoning_content', None)
                if reasoning:
                    reasoning_content += reasoning
                    if first_reasoning:
                        print("\n🤔:", file=sys.stdout, flush=True)
                        first_reasoning = False
                    print(reasoning, end="", file=sys.stdout, flush=True)

            print(file=sys.stdout)
            print(f"\n[DEBUG] full_content length: {len(full_content)}, content: {full_content[:200] if full_content else 'EMPTY'}", file=sys.stderr)
            print(f"[DEBUG] reasoning_content length: {len(reasoning_content)}, content: {reasoning_content[:200] if reasoning_content else 'EMPTY'}", file=sys.stderr)
            print(f"[DEBUG] tool_calls_buffer: {tool_calls_buffer}", file=sys.stderr)

            # 解析工具调用参数
            tool_calls = list(tool_calls_buffer.values()) if tool_calls_buffer else None
            if tool_calls:
                for tc in tool_calls:
                    try:
                        tc["function"]["arguments"] = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        pass

            return ChatResponse(
                content=full_content.strip(),
                tool_calls=tool_calls,
                reasoning_content=reasoning_content.strip(),
            )

        except Exception as e:
            print(f"\n[错误] 请求失败：{e}", file=sys.stderr)
            raise

    def _chat_non_stream(self, client, kwargs: Dict) -> ChatResponse:
        """非流式输出（非 debug 模式）"""
        kwargs["stream"] = False

        try:
            response = client.chat.completions.create(**kwargs)

            # 提取内容
            full_content = ""
            reasoning_content = ""
            tool_calls = None

            if response.choices:
                choice = response.choices[0]
                if choice.message:
                    full_content = choice.message.content or ""
                    # 推理内容（部分模型支持）
                    reasoning_content = getattr(choice.message, 'reasoning_content', '') or \
                                        getattr(choice.message, 'reasoning', '') or \
                                        getattr(choice.message, 'thought', '') or ""

                    # 工具调用
                    if choice.message.tool_calls:
                        tool_calls = []
                        for tc in choice.message.tool_calls:
                            tool_calls.append({
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                                }
                            })

            return ChatResponse(
                content=full_content.strip(),
                tool_calls=tool_calls,
                reasoning_content=reasoning_content.strip(),
            )

        except Exception as e:
            raise