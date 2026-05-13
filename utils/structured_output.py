#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for extracting structured data from agent runtime results."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def extract_structured_model(result: Any, model_type: type[ModelT]) -> ModelT:
    """Validate structured runtime output, including JSON embedded in messages."""

    candidates = list(_iter_candidates(result))
    for candidate in candidates:
        try:
            return model_type.model_validate(candidate)
        except Exception:
            continue

    raise ValueError(f"runtime did not return valid {model_type.__name__}")


def _iter_candidates(value: Any):
    if isinstance(value, BaseModel):
        yield value.model_dump()
        return

    if isinstance(value, dict):
        for key in ("structured", "structured_response", "structured_output", "output", "result", "message"):
            if key in value:
                yield value[key]
        yield from _iter_structured_outputs(value)
        for message in value.get("messages", []) or []:
            yield from _iter_message_content(message)
        for part in value.get("parts", []) or []:
            yield from _iter_message_content(part)
        yield value
        return

    yield from _iter_message_content(value)


def _iter_structured_outputs(value: Any):
    if isinstance(value, dict):
        for key in ("structured", "structured_output"):
            structured = value.get(key)
            if structured is not None:
                yield structured
        for item in value.values():
            yield from _iter_structured_outputs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_structured_outputs(item)


def _iter_message_content(message: Any):
    if isinstance(message, dict) and isinstance(message.get("text"), str):
        yield from _iter_message_content(message["text"])

    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", message)
    if not isinstance(content, str):
        return

    stripped = content.strip()
    if not stripped:
        return

    parsed = _try_parse_json(stripped)
    if parsed is not None:
        yield parsed

    for block in re.findall(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE):
        parsed = _try_parse_json(block.strip())
        if parsed is not None:
            yield parsed


def _try_parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
