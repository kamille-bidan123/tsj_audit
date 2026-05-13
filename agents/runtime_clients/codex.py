#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Codex CLI runtime client."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agents.runtime_clients.command import CommandRuntimeClient


class CodexRuntimeClient(CommandRuntimeClient):
    runtime = "codex"

    def run_raw(
        self,
        *,
        prompt: str,
        output_model: type[BaseModel],
        config,
        stage_name: str,
    ) -> Any:
        output_file = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        output_path = output_file.name
        output_file.close()
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as schema_file:
            json.dump(self._output_schema(output_model), schema_file, ensure_ascii=False)
            schema_path = schema_file.name

        command = self.build_command(
            schema_path,
            stage_name=stage_name,
            output_path=output_path,
        )
        try:
            return self._run_command(command, config, input_text=prompt, output_path=output_path)
        finally:
            for path in (schema_path, output_path):
                try:
                    Path(path).unlink()
                except OSError:
                    pass

    def build_command(
        self,
        schema_path: str,
        *,
        stage_name: str = "trace",
        output_path: str | None = None,
    ) -> list[str]:
        command = ["codex", "exec"]
        sandbox = "workspace-write" if stage_name == "exploit" else "read-only"
        command = self._append_config_override(command, 'approval_policy="never"')
        command = self._append_flag(command, "--skip-git-repo-check")
        command = self._append_option(command, "--sandbox", sandbox)
        command = self._append_option(command, "--color", "never")
        if output_path:
            command = self._append_option(command, "--output-last-message", output_path)
        return [*command, "--output-schema", schema_path, "-"]
