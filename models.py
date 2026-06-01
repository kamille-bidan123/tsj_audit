#!/usr/bin/env python3
"""Minimal Python compatibility models for legacy scan scripts.

The Go implementation is the primary application. This file exists only so
custom or retained Python scan scripts can still construct EntrySpec objects
and serialize them with model_dump().
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class EntrySpec:
    func_name: str
    file_path: str
    skill: Optional[str] = None
    start_line: Optional[int] = None

    def model_dump(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}
