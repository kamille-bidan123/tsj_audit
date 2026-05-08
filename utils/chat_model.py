#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chat model factory shared by DeepAgents runners."""

from __future__ import annotations

from typing import Any


def build_chat_model():
    """Build the OpenAI-compatible chat model from project config."""
    from config import get_config
    from langchain_openai import ChatOpenAI

    config = get_config()
    model_kwargs: dict[str, Any] = {
        "model": config.model_name,
        "api_key": config.api_key,
        "base_url": config.base_url,
        "temperature": _temperature_for(config),
        "use_responses_api": False,
    }
    model_kwargs.update(_provider_options(config))
    return ChatOpenAI(**model_kwargs)


def _temperature_for(config) -> float | None:
    model_name = config.model_name.lower()
    if model_name == "deepseek-reasoner":
        return None
    if _is_deepseek(config) and config.deepseek_thinking == "enabled":
        return None
    return 0.1


def _provider_options(config) -> dict[str, Any]:
    if not _is_deepseek(config):
        return {}

    options: dict[str, Any] = {
        "extra_body": {"thinking": {"type": config.deepseek_thinking}},
    }
    if config.deepseek_thinking == "enabled" and config.deepseek_reasoning_effort:
        options["reasoning_effort"] = config.deepseek_reasoning_effort
    return options


def _is_deepseek(config) -> bool:
    return (
        "deepseek" in config.base_url.lower()
        or config.model_name.lower().startswith("deepseek")
    )
