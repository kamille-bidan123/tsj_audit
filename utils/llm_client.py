#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 客户端模块

使用 OpenAI Python 库进行聊天，默认使用流式响应。
配置通过 config 模块的单例获取。
"""

import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Message:
    """聊天消息"""
    role: str
    content: str


@dataclass
class ChatResponse:
    """聊天响应"""
    content: str
    thought: Optional[str] = None
    model: str = ""
    usage: Optional[Dict[str, Any]] = None


class LLMClient:
    """
    LLM 客户端，使用 OpenAI Python 库

    默认使用流式输出，配置通过 config 模块单例获取。
    """

    def __init__(self):
        """初始化 LLM 客户端，无需传递参数"""

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        发送聊天请求（流式输出）

        Args:
            messages: 消息列表，每项为 {"role": "user|assistant", "content": "..."}
            system_prompt: 系统提示词（可选）
            temperature: 温度参数 (0-2)
            max_tokens: 最大生成 token 数

        Returns:
            ChatResponse 响应对象
        """
        # 重置取消状态
        self._cancelled = False

        # 从 config 模块单例获取配置
        from config import get_config
        config = get_config()

        # 构建请求体
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        # 每次调用都创建新客户端以保证配置最新
        print(f"使用模型: {config.model_name}", file=sys.stderr)
        from openai import OpenAI
        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

        return self._chat_stream(
            api_messages,
            config.model_name,
            temperature,
            max_tokens,
            config.debug,
            client,
        )

    def _chat_stream(
        self,
        messages: List[Dict[str, str]],
        model_name: str,
        temperature: float,
        max_tokens: Optional[int],
        debug: bool,
        client,
    ) -> ChatResponse:
        """流式聊天，支持 reasoning_content 和 <think> 标签两种思考格式"""
        full_thought = ""
        full_content = ""
        first_reasoning = True
        first_content = True

        try:
            stream_kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            }
            if max_tokens:
                stream_kwargs["max_tokens"] = max_tokens

            stream = client.chat.completions.create(**stream_kwargs)

            for chunk in stream:

                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # 优先使用 reasoning_content 属性（DeepSeek 等模型的推理模式）
                reasoning_content = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None)
                if reasoning_content:
                    full_thought += reasoning_content
                    if debug:
                        if first_reasoning:
                            print("\n🤔:", file=sys.stderr, flush=True)
                            first_reasoning = False
                        print(reasoning_content, end="", file=sys.stderr, flush=True)

                # 正文内容
                content = getattr(delta, 'content', None)
                if content:
                    full_content += content
                    if debug:
                        if first_content:
                            print("\n📝:", file=sys.stdout, flush=True)
                            first_content = False
                        print(content, end="", file=sys.stdout, flush=True)

            if debug:
                print(file=sys.stdout)
                print(file=sys.stderr)

            thought = full_thought.strip() if full_thought else None
            content = full_content.strip()

            return ChatResponse(
                content=content,
                thought=thought,
                model=model_name,
            )

        except Exception as e:
            if debug:
                print(f"\n[错误] 流式请求失败：{e}", file=sys.stderr)
            raise