#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared prompt/schema helpers and facade for agent runtime clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from utils.structured_output import extract_structured_model


class BaseRuntimeClient:
    """Base class shared by concrete agent runtime providers."""

    runtime: str

    def __init__(self, *, project_path: str, debug: bool = False):
        self.project_path = Path(project_path).expanduser().resolve()
        self.debug = debug

    def run_json(
        self,
        *,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
    ) -> tuple[BaseModel, list[Dict[str, Any]]]:
        from config import get_config

        config = get_config()
        prompt = self._build_prompt(stage_name, system_prompt, user_prompt, output_model)
        raw = self.run_raw(
            prompt=prompt,
            output_model=output_model,
            config=config,
            stage_name=stage_name,
        )
        output = extract_structured_model(raw, output_model)
        return output, [{"role": "assistant", "content": raw}]

    def run_raw(
        self,
        *,
        prompt: str,
        output_model: type[BaseModel],
        config,
        stage_name: str,
    ) -> Any:
        raise NotImplementedError

    def _build_prompt(
        self,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
    ) -> str:
        schema = json.dumps(self._output_schema(output_model), ensure_ascii=False)
        return (
            "## Unified System Prompt\n"
            f"{system_prompt}\n\n"
            f"## Runtime\n"
            f"- 当前由 {self.runtime} 运行 {stage_name} 阶段。\n"
            f"- 工作目录已绑定到待审计项目：{self.project_path}。\n"
            "- 如果需要查看源码，请只读取当前项目内文件。\n"
            "- 最终回答必须是满足下方 JSON Schema 的 JSON 对象，不要输出 Markdown。\n"
            "- 所有 FunctionInfo、CodeMap、skill、runtime、schema 等字段注入都只存在于本统一 system prompt 中。\n\n"
            f"## JSON Schema\n{schema}\n\n"
            f"## User Task\n{user_prompt}"
        )

    def _output_schema(self, output_model: type[BaseModel]) -> dict[str, Any]:
        return to_strict_json_schema(output_model)


class AgentRuntimeClient:
    """Thin facade selecting the configured concrete runtime client."""

    def __init__(self, runtime: str, *, project_path: str, debug: bool = False):
        self.runtime = runtime
        self._client = self._create_client(runtime, project_path=project_path, debug=debug)

    def run_json(
        self,
        *,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        output_model: type[BaseModel],
    ) -> tuple[BaseModel, list[Dict[str, Any]]]:
        return self._client.run_json(
            stage_name=stage_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_model=output_model,
        )

    def _output_schema(self, output_model: type[BaseModel]) -> dict[str, Any]:
        return self._client._output_schema(output_model)

    @property
    def provider(self) -> BaseRuntimeClient:
        return self._client

    def _create_client(self, runtime: str, *, project_path: str, debug: bool) -> BaseRuntimeClient:
        if runtime == "opencode":
            from agents.runtime_clients.opencode import OpenCodeRuntimeClient

            return OpenCodeRuntimeClient(project_path=project_path, debug=debug)
        if runtime == "codex":
            from agents.runtime_clients.codex import CodexRuntimeClient

            return CodexRuntimeClient(project_path=project_path, debug=debug)
        if runtime == "claudecode":
            from agents.runtime_clients.claudecode import ClaudeCodeRuntimeClient

            return ClaudeCodeRuntimeClient(project_path=project_path, debug=debug)
        raise ValueError(f"unsupported agent runtime: {runtime}")
