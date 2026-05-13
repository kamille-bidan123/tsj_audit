#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime-specific skill installation and prompt helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any
from pathlib import Path

import yaml

from models import FunctionInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SKILLS_DIR = PROJECT_ROOT / "skills"
ATTACK_SURFACE_SKILLS_DIR = SOURCE_SKILLS_DIR / "attack_surface"


@dataclass(frozen=True)
class RuntimeSkillInstall:
    skill: str
    skill_dir: Path
    skill_file: Path
    relative_skill_file: str


@dataclass(frozen=True)
class AttackSurfaceSkillMetadata:
    name: str
    required_audit_types: tuple[str, ...]


def runtime_skill_base_dir(runtime: str) -> Path:
    """Return the project-local skill directory for a runtime."""

    normalized = (runtime or "codex").strip().lower()
    if normalized == "opencode":
        return Path(".opencode") / "skills"
    if normalized == "claudecode":
        return Path(".claude") / "skills"
    if normalized == "codex":
        return Path(".agents") / "skills"
    raise ValueError(f"unsupported agent runtime for skill installation: {runtime}")


def ensure_runtime_skill(
    func_info: FunctionInfo,
    *,
    runtime: str,
    project_path: str,
) -> RuntimeSkillInstall | None:
    """Copy FunctionInfo.skill into the target project's runtime-specific skill path."""

    return ensure_runtime_skill_by_name(
        func_info.skill or "",
        runtime=runtime,
        project_path=project_path,
        attack_surface=True,
    )


def ensure_runtime_skill_by_name(
    skill: str,
    *,
    runtime: str,
    project_path: str,
    attack_surface: bool = False,
) -> RuntimeSkillInstall | None:
    """Copy a named skill into the target project's runtime-specific skill path."""

    skill = (skill or "").strip()
    if not skill:
        return None

    source_dir = _skill_source_dir(skill, attack_surface=attack_surface)
    source_file = source_dir / "SKILL.md"

    project = Path(project_path).expanduser().resolve()
    ensure_runtime_general_skills(runtime=runtime, project_path=project)
    target_dir = project / runtime_skill_base_dir(runtime) / skill
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    _copy_skill_dir(source_dir, target_dir)

    skill_file = target_dir / "SKILL.md"
    return RuntimeSkillInstall(
        skill=skill,
        skill_dir=target_dir,
        skill_file=skill_file,
        relative_skill_file=skill_file.relative_to(project).as_posix(),
    )


def ensure_runtime_general_skills(*, runtime: str, project_path: str | Path) -> list[RuntimeSkillInstall]:
    """Copy normal skills from skills/* into the target project, excluding attack_surface."""

    project = Path(project_path).expanduser().resolve()
    installed: list[RuntimeSkillInstall] = []
    if not SOURCE_SKILLS_DIR.exists():
        return installed
    for source_dir in sorted(path for path in SOURCE_SKILLS_DIR.iterdir() if path.is_dir()):
        if source_dir.name == "attack_surface":
            continue
        source_file = source_dir / "SKILL.md"
        if not source_file.exists():
            continue
        target_dir = project / runtime_skill_base_dir(runtime) / source_dir.name
        _copy_skill_dir(source_dir, target_dir)
        skill_file = target_dir / "SKILL.md"
        installed.append(
            RuntimeSkillInstall(
                skill=source_dir.name,
                skill_dir=target_dir,
                skill_file=skill_file,
                relative_skill_file=skill_file.relative_to(project).as_posix(),
            )
        )
    return installed


def _copy_skill_dir(source_dir: Path, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        target_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _skill_source_dir(skill: str, *, attack_surface: bool) -> Path:
    base = ATTACK_SURFACE_SKILLS_DIR if attack_surface else SOURCE_SKILLS_DIR
    source_dir = base / skill
    source_file = source_dir / "SKILL.md"
    if not source_file.exists():
        kind = "attack surface skill" if attack_surface else "skill"
        raise RuntimeError(f"{kind} not found: {source_file}")
    return source_dir


def load_attack_surface_skill_metadata(skill: str) -> AttackSurfaceSkillMetadata:
    """Read attack-surface metadata from SKILL.md frontmatter."""

    skill = (skill or "").strip()
    if not skill:
        return AttackSurfaceSkillMetadata(name="", required_audit_types=())

    source_file = ATTACK_SURFACE_SKILLS_DIR / skill / "SKILL.md"
    if not source_file.exists():
        raise RuntimeError(f"function skill not found: {source_file}")

    metadata = _read_skill_frontmatter(source_file)
    required = metadata.get("required_audit_types") or []
    if isinstance(required, str):
        required = [item.strip() for item in required.split(",") if item.strip()]
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise RuntimeError(f"{source_file} required_audit_types must be a string list")

    return AttackSurfaceSkillMetadata(
        name=str(metadata.get("name") or skill),
        required_audit_types=tuple(dict.fromkeys(item.strip() for item in required if item.strip())),
    )


def _read_skill_frontmatter(skill_file: Path) -> dict[str, Any]:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"failed to parse skill frontmatter {skill_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"skill frontmatter must be a mapping: {skill_file}")
    return data


def build_skill_usage_prompt(
    func_info: FunctionInfo,
    *,
    runtime: str,
    project_path: str,
) -> str:
    """Build a runtime-neutral instruction telling the LLM to use the attack-surface skill."""

    return build_attack_surface_skill_usage_prompt(
        func_info.skill or "",
        runtime=runtime,
        project_path=project_path,
    )


def build_skill_usage_prompt_by_name(
    skill: str,
    *,
    runtime: str,
    project_path: str,
) -> str:
    """Build a runtime-neutral instruction telling the LLM to use a named attack-surface skill."""

    installed = ensure_runtime_skill_by_name(skill, runtime=runtime, project_path=project_path)
    if not installed:
        return ""

    return f"""## Function Skill
当前任务声明了普通 skill：`{installed.skill}`。
该 skill 已安装到当前被审计项目内：`{installed.relative_skill_file}`。

强制要求：
- 在 discovery/trace/audit/exploit 前必须使用 `{installed.skill}` skill 中的攻击面发现知识、外部输入知识、数据流分析知识和 PoC 生成知识。
- 如果当前 runtime 提供 skill 工具，请先加载 `{installed.skill}`。
- 如果当前 runtime 不提供 skill 工具，请直接读取 `{installed.relative_skill_file}`，并按其中的知识进行数据流追踪。
- 不要把 skill 文档本身当成具体污染源；具体 taint_source 必须来自当前函数代码中的变量、参数或 API 调用。
"""


def build_attack_surface_skill_usage_prompt(
    skill: str,
    *,
    runtime: str,
    project_path: str,
) -> str:
    installed = ensure_runtime_skill_by_name(
        skill,
        runtime=runtime,
        project_path=project_path,
        attack_surface=True,
    )
    if not installed:
        return ""
    return f"""## Attack Surface Skill
当前任务声明了攻击面 skill：`{installed.skill}`。
该攻击面 skill 已安装到当前被审计项目内：`{installed.relative_skill_file}`。

强制要求：
- 在 discovery/trace/audit/exploit 前必须使用 `{installed.skill}` 中的攻击面发现知识、外部输入知识、数据流分析知识和 PoC 生成知识。
- 如果当前 runtime 提供 skill 工具，请先加载 `{installed.skill}`。
- 如果当前 runtime 不提供 skill 工具，请直接读取 `{installed.relative_skill_file}`，并按其中的知识进行数据流追踪。
- 不要把 skill 文档本身当成具体污染源；具体 taint_source 必须来自当前函数代码中的变量、参数或 API 调用。
"""
