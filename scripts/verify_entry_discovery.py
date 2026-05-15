#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify attack-surface skill driven entry discovery."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import agents.agent_runtime_runner as runner_module
from agents.entry_discovery_agent import EntryDiscoveryAgent
from agents.output_schemas import EntryDiscoveryOutput
from config import init_settings
from main import discover_attack_surface_entries
from models import EntrySpec


PROJECT_ROOT = Path(__file__).parent.parent


def fake_entry() -> EntrySpec:
    return EntrySpec(
        func_name="add_user",
        file_path="src/web.c",
        start_line=10,
        skill="civetweb_audit",
    )


class FakeRuntimeClient:
    calls: list[dict] = []

    def __init__(self, runtime: str, *, project_path: str, debug: bool = False):
        self.runtime = runtime
        self.project_path = project_path
        self.debug = debug

    def run_json(self, *, stage_name, system_prompt, user_prompt, output_model):
        self.calls.append(
            {
                "stage_name": stage_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "output_model": output_model,
            }
        )
        return EntryDiscoveryOutput(functions=[fake_entry()]), [{"role": "assistant", "content": "fake"}]


def verify_entry_discovery_runner_returns_entry_spec_list() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        init_settings(
            {
                "project_path": tmpdir,
                "agent_runtime": "codex",
                "attack_surface_skill": "civetweb_audit",
                "scan": "",
            }
        )
        FakeRuntimeClient.calls = []
        original_client = runner_module.AgentRuntimeClient
        runner_module.AgentRuntimeClient = FakeRuntimeClient
        try:
            entries = EntryDiscoveryAgent(
                attack_surface_skill="civetweb_audit",
                project_path=tmpdir,
            ).discover()
        finally:
            runner_module.AgentRuntimeClient = original_client

        if entries != [fake_entry()]:
            raise AssertionError("entry discovery should return an EntrySpec list")
        call = FakeRuntimeClient.calls[0]
        if call["stage_name"] != "entry_discovery":
            raise AssertionError("entry discovery should use the entry_discovery runtime stage")
        if call["output_model"] is not EntryDiscoveryOutput:
            raise AssertionError("entry discovery should use EntryDiscoveryOutput schema")
        if "civetweb_audit" not in call["system_prompt"]:
            raise AssertionError("entry discovery prompt should inject the attack surface skill")
        if "攻击面发现知识" not in call["system_prompt"]:
            raise AssertionError("entry discovery prompt should require attack-surface discovery knowledge")


def verify_main_saves_discovered_entry_spec_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        config = init_settings(
            {
                "project_path": tmpdir,
                "output_dir": str(output_dir),
                "agent_runtime": "codex",
                "attack_surface_skill": "civetweb_audit",
                "scan": "",
            }
        )
        FakeRuntimeClient.calls = []
        original_client = runner_module.AgentRuntimeClient
        runner_module.AgentRuntimeClient = FakeRuntimeClient
        try:
            discovered_path = discover_attack_surface_entries(config)
        finally:
            runner_module.AgentRuntimeClient = original_client

        path = Path(discovered_path)
        if path != output_dir / "discovered_functions.json":
            raise AssertionError(f"unexpected discovered output path: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data[0]["func_name"] != "add_user" or data[0]["skill"] != "civetweb_audit":
            raise AssertionError("discovered_functions.json should contain discovered EntrySpec entries")
        if "code_snippet" in data[0] or "end_line" in data[0] or "input" in data[0]:
            raise AssertionError("entry discovery should save lightweight EntrySpec fields only")


def verify_resume_reuses_discovered_function_info_json() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir()
        discovered_file = output_dir / "discovered_functions.json"
        discovered_file.write_text(
            json.dumps([fake_entry().model_dump()], ensure_ascii=False),
            encoding="utf-8",
        )
        config = init_settings(
            {
                "project_path": tmpdir,
                "output_dir": str(output_dir),
                "agent_runtime": "codex",
                "attack_surface_skill": "civetweb_audit",
                "scan": "",
                "resume": True,
            }
        )
        FakeRuntimeClient.calls = []
        discovered_path = discover_attack_surface_entries(config)

        if Path(discovered_path) != discovered_file:
            raise AssertionError("resume should reuse discovered_functions.json")
        if FakeRuntimeClient.calls:
            raise AssertionError("resume should not call entry discovery when discovered_functions.json exists")


def verify_civetweb_skill_has_required_attack_surface_sections() -> None:
    skill_path = PROJECT_ROOT / "skills" / "attack_surface" / "civetweb_audit" / "SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")
    required_sections = ["## 攻击面发现知识", "## 外部输入知识", "## PoC 生成知识"]
    missing = [section for section in required_sections if section not in skill_text]
    if missing:
        raise AssertionError(f"civetweb skill missing required sections: {missing}")
    if not (PROJECT_ROOT / "skills" / "attack_surface" / "civetweb_audit" / "scripts" / "scan.py").exists():
        raise AssertionError("previous CivetWeb scan script should be available as a skill subfile")


if __name__ == "__main__":
    verify_entry_discovery_runner_returns_entry_spec_list()
    verify_main_saves_discovered_entry_spec_json()
    verify_resume_reuses_discovered_function_info_json()
    verify_civetweb_skill_has_required_attack_surface_sections()
    print("entry discovery verification passed")
