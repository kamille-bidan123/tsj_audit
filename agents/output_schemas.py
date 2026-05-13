#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured output schemas shared by external agent runtimes."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from models import CodeContext, FunctionInfo


class EntryDiscoveryOutput(BaseModel):
    """Structured output expected from attack-surface entry discovery."""

    functions: List[FunctionInfo] = Field(
        default_factory=list,
        description="自动发现的攻击面入口函数列表",
    )


class TraceOutput(BaseModel):
    """Structured output expected from trace exploration."""

    code_logic: str = Field(description="函数的业务逻辑描述")
    code_map: List[CodeContext] = Field(description="所有被污染的函数调用链上下文")


class AuditOutput(BaseModel):
    """Structured output expected from vulnerability audit."""

    is_vulnerable: bool = Field(description="是否存在漏洞")
    confidence: str = Field(description="漏洞置信度：high、medium 或 low")
    description: str = Field(default="", description="漏洞描述")
    summary: str = Field(default="", description="审计发现总结")
    taint_flow: Optional[str] = Field(default=None, description="污点流向")
    recommendation: Optional[str] = Field(default=None, description="修复建议")
    code_map: List[CodeContext] = Field(
        default_factory=list,
        description="相关代码上下文列表",
    )
    findings: List['AuditFindingOutput'] = Field(
        default_factory=list,
        description="同一漏洞类型下的多个独立审计发现；如果为空，则使用顶层字段作为兼容的单条结果",
    )


class AuditFindingOutput(BaseModel):
    """One concrete finding emitted by a vulnerability audit."""

    finding_id: Optional[str] = Field(default=None, description="同一漏洞类型下稳定的发现 ID")
    title: str = Field(default="", description="发现标题")
    severity: Optional[str] = Field(default=None, description="严重程度：critical、high、medium、low 或 info")
    is_vulnerable: bool = Field(description="该发现是否确认为漏洞")
    confidence: str = Field(description="该发现置信度：high、medium 或 low")
    description: str = Field(default="", description="该发现描述")
    taint_flow: Optional[str] = Field(default=None, description="该发现对应的污点流向")
    recommendation: Optional[str] = Field(default=None, description="该发现修复建议")
    code_map: List[CodeContext] = Field(
        default_factory=list,
        description="该发现相关代码上下文列表",
    )


class ExploitOutput(BaseModel):
    """Structured output expected from exploit verification."""

    success: bool = Field(description="利用验证是否成功")
    poc_command: str = Field(default="", description="最终使用的 PoC 命令")
    summary: str = Field(default="", description="利用过程总结或验证输出")
    error: Optional[str] = Field(default=None, description="错误信息")
