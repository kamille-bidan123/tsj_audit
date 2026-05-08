#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helpers for extracting structured data from DeepAgents results."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def extract_structured_model(result: Any, model_type: type[ModelT]) -> ModelT:
    """Validate DeepAgents output, including JSON embedded in message content."""
    candidates = list(_iter_candidates(result))
    last_error: ValidationError | None = None

    for candidate in candidates:
        try:
            return model_type.model_validate(candidate)
        except ValidationError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return model_type.model_validate(result)


def _iter_candidates(result: Any):
    if isinstance(result, dict):
        for key in ("structured_response", "output"):
            value = result.get(key)
            if value is not None:
                yield value

        yield from _iter_message_payloads(result.get("messages", []))
        yield result
        return

    yield result


def _iter_message_payloads(messages: Any):
    if not isinstance(messages, list):
        return

    for message in reversed(messages):
        content = _message_content(message)
        yield from _iter_content_payloads(content)


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _iter_content_payloads(content: Any):
    if isinstance(content, dict):
        yield content
        text = content.get("text") or content.get("content")
        if text is not None:
            parsed = _parse_json_text(str(text))
            if parsed is not None:
                yield parsed
        return

    if isinstance(content, list):
        for item in reversed(content):
            yield from _iter_content_payloads(item)
        return

    if isinstance(content, str):
        parsed = _parse_json_text(content)
        if parsed is not None:
            yield parsed


def _parse_json_text(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None

    for candidate in _json_text_candidates(stripped):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _json_text_candidates(text: str) -> list[str]:
    candidates = [text]

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    return candidates
