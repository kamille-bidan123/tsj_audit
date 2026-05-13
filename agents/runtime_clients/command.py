#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Subprocess helpers for CLI-backed agent runtimes."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from agents.runtime_clients.base import BaseRuntimeClient


class CommandRuntimeClient(BaseRuntimeClient):
    """Base class for command-line runtimes."""

    def _run_command(
        self,
        command: list[str],
        config,
        *,
        input_text: str | None = None,
        output_path: str | None = None,
    ) -> Any:
        self._validate_command(command)
        timeout = config.external_runtime_timeout_seconds
        started_at = time.monotonic()
        safe_command = self._format_command_for_log(command, debug=bool(getattr(config, "debug", False)))
        print(
            f"[{self.runtime}] agent runtime started: {safe_command} "
            f"(timeout={timeout}s)",
            file=sys.stderr,
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=self.project_path,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"agent runtime command not found: {command[0]}") from exc
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"agent runtime command could not start: {exc}") from exc

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        stdout_thread = threading.Thread(
            target=self._collect_stream,
            args=(process.stdout, stdout_chunks, False),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._collect_stream,
            args=(process.stderr, stderr_chunks, bool(getattr(config, "debug", False))),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            if process.stdin is not None and input_text is not None:
                process.stdin.write(input_text)
                process.stdin.close()

            last_heartbeat = started_at
            while process.poll() is None:
                now = time.monotonic()
                if now - started_at > timeout:
                    process.kill()
                    raise RuntimeError(f"agent runtime command timed out after {timeout}s: {command[0]}")
                if now - last_heartbeat >= 30:
                    elapsed = int(now - started_at)
                    print(f"[{self.runtime}] agent runtime still running ({elapsed}s)", file=sys.stderr)
                    last_heartbeat = now
                time.sleep(0.2)
        except KeyboardInterrupt:
            process.kill()
            raise

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        stdout = "".join(stdout_chunks).strip()
        stderr = "".join(stderr_chunks).strip()
        if process.returncode != 0:
            raise RuntimeError(
                f"agent runtime command failed ({process.returncode}): "
                f"{stderr or stdout}"
            )

        stdout = self._read_output_path(output_path) or stdout
        if not stdout:
            raise RuntimeError(f"agent runtime command returned empty output: {command[0]}")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return stdout

    def _append_flag(self, command: list[str], flag: str) -> list[str]:
        if flag in command:
            return command
        return [*command, flag]

    def _append_option(self, command: list[str], option: str, value: str) -> list[str]:
        if option in command:
            return command
        return [*command, option, value]

    def _append_config_override(self, command: list[str], override: str) -> list[str]:
        key = override.split("=", 1)[0]
        for index, arg in enumerate(command):
            if arg in {"-c", "--config"} and index + 1 < len(command):
                if command[index + 1].split("=", 1)[0] == key:
                    return command
            if arg.startswith("--config=") and arg.removeprefix("--config=").split("=", 1)[0] == key:
                return command
        return [*command, "-c", override]

    def _collect_stream(self, stream, chunks: list[str], forward: bool) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                chunks.append(line)
                if forward:
                    print(line, end="", file=sys.stderr)
        finally:
            stream.close()

    def _read_output_path(self, output_path: str | None) -> str:
        if not output_path:
            return ""
        try:
            return Path(output_path).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _format_command_for_log(self, command: list[str], *, debug: bool = False) -> str:
        if debug:
            return " ".join(shlex.quote(arg) for arg in command)
        redacted: list[str] = []
        redact_next = False
        for arg in command:
            if redact_next:
                redacted.append("<redacted>")
                redact_next = False
                continue
            redacted.append(arg)
            if arg == "--prompt":
                redact_next = True
        if self.runtime == "claudecode" and redacted:
            redacted[-1] = "<redacted-prompt>"
        return " ".join(shlex.quote(arg) for arg in redacted)

    def _validate_command(self, command: list[str]) -> None:
        if not command:
            raise RuntimeError("agent runtime command is empty")
        for arg in command:
            if "\0" in arg:
                raise RuntimeError("agent runtime command contains NUL byte")
