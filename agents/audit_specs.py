#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YAML-driven vulnerability audit spec registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from models import CodeContext, FunctionInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = PROJECT_ROOT / "audit_specs"
PromptBuilder = Callable[[FunctionInfo, List[CodeContext]], str]


@dataclass(frozen=True)
class AuditSpec:
    """Configuration contract for one vulnerability audit type."""

    audit_type: str
    build_user_message: PromptBuilder
    source_path: Optional[Path] = None

    @property
    def agent_name(self) -> str:
        """Runtime stage name generated from audit_type."""
        return f"{self.audit_type}_audit"

    @property
    def display_name(self) -> str:
        """Human-readable name generated from audit_type."""
        return self.audit_type.replace("_", " ").title()

    @property
    def enable_exploit(self) -> bool:
        """Normal registered audit specs allow exploit verification by default."""
        return True

    @property
    def exploit_confidence(self) -> tuple[str, ...]:
        """Confidence levels that can trigger exploit verification."""
        return ("high", "medium")

    def build_system_prompt(self, _func_info: FunctionInfo, _code_map: List[CodeContext]) -> str:
        """Build the shared vulnerability-type system prompt from audit_type."""
        return _build_default_system_prompt(self.audit_type)


def load_audit_specs(spec_dir: Path = SPEC_DIR) -> Dict[str, AuditSpec]:
    """Load all audit specs from YAML files."""

    specs: Dict[str, AuditSpec] = {}
    if not spec_dir.exists():
        raise RuntimeError(f"audit spec directory not found: {spec_dir}")

    for path in sorted(spec_dir.glob("*.yaml")):
        data = _load_yaml(path)
        spec = _spec_from_data(data, path)
        if spec.audit_type in specs:
            raise RuntimeError(f"duplicate audit_type in YAML specs: {spec.audit_type}")
        specs[spec.audit_type] = spec

    if not specs:
        raise RuntimeError(f"no audit specs found in {spec_dir}")
    return specs


def _spec_from_data(data: dict[str, Any], path: Path) -> AuditSpec:
    required = ("name", "user_prompt")
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise RuntimeError(f"{path} missing required fields: {', '.join(missing)}")

    extra = set(data) - set(required)
    if extra:
        raise RuntimeError(
            f"{path} unsupported fields for minimal audit spec: {', '.join(sorted(extra))}. "
            "Only name and user_prompt are allowed."
        )

    audit_type = str(data["name"])
    user_template = str(data["user_prompt"])

    return AuditSpec(
        audit_type=audit_type,
        build_user_message=_make_prompt_builder(user_template, audit_type),
        source_path=path,
    )


def _build_default_system_prompt(audit_type: str) -> str:
    display_name = audit_type.replace("_", " ")
    return f"""你是一个代码安全审计专家，专门进行 {display_name} 类型的漏洞审计。

## 任务
从公共 system prompt 中指定的入口函数开始，基于公共上下文中的 Function Skill、Code Map 和项目源码，判断当前入口函数是否存在 {display_name} 安全问题。

## 通用审计要求
1. 只关注公共 system prompt 中指定入口函数相关的数据流、控制流和代码路径。
2. 必须从外部输入如何到达敏感操作、状态变更或安全决策开始分析。
3. 不要全局搜索危险函数、关键词或模式后直接下结论；必须证明其与当前入口函数有关。
4. 如果同一漏洞类型下存在多个独立 source/sink、控制流或利用条件，必须在 findings 数组中逐条输出。
5. 如果无法证明安全影响，应返回低置信度或无漏洞，不要编造问题。

## 类型标识
- 当前漏洞类型：{audit_type}
- findings 中的具体问题标题应写清楚风险点、sink 或失败的安全条件。"""


def _make_prompt_builder(template: str, audit_type: str) -> PromptBuilder:
    def build(_func_info: FunctionInfo, _code_map: List[CodeContext]) -> str:
        return _render_template(
            template,
            {
                "audit_type": audit_type,
            },
        )

    return build


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"failed to parse audit spec YAML {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"audit spec YAML must be a mapping: {path}")
    return data


AUDIT_SPECS: Dict[str, AuditSpec] = load_audit_specs()
DEFAULT_AUDIT_TYPES = [
    audit_type for audit_type in AUDIT_SPECS
]
