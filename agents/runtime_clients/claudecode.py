#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code CLI runtime client."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agents.runtime_clients.command import CommandRuntimeClient


class ClaudeCodeRuntimeClient(CommandRuntimeClient):
    runtime = "claudecode"

    def run_raw(
        self,
        *,
        prompt: str,
        output_model: type[BaseModel],
        config,
        stage_name: str,
    ) -> Any:
        return self._run_command(self.build_command(prompt), config)

    def build_command(self, prompt: str) -> list[str]:
        return [
            "claude",
            "-p",
            "--output-format",
            "json",
            prompt,
        ]
