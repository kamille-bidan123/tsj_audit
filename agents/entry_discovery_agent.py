#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Attack-surface skill driven FunctionInfo discovery."""

from __future__ import annotations

from typing import List

from agents.runtime_factory import create_entry_discovery_runner
from models import EntrySpec


class EntryDiscoveryAgent:
    """Discover audit entry functions from an attack-surface skill."""

    def __init__(
        self,
        *,
        attack_surface_skill: str,
        project_path: str = ".",
        debug: bool = False,
        output_dir: str | None = None,
    ):
        self.attack_surface_skill = attack_surface_skill
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def discover(self) -> List[EntrySpec]:
        return create_entry_discovery_runner(
            attack_surface_skill=self.attack_surface_skill,
            project_path=self.project_path,
            debug=self.debug,
            output_dir=self.output_dir,
        ).run()
