#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享数据模型

定义 scan 和 trace 共用的 Pydantic 模型
"""

from typing import Optional, List
from pydantic import BaseModel


class FunctionInfo(BaseModel):
    """回调函数信息"""
    func_name: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str
    # 外部输入点标识（如 "mg_get_var", "mg_websocket_accept" 等）
    # 本质是知识文档的引用，标识这个函数的外部输入来源
    input: str


class CodeContext(BaseModel):
    """代码上下文信息"""
    function_name: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    is_entry_point: bool = False
    taint_source: Optional[str] = None
    taint_path: Optional[str] = None


class TraceResult(BaseModel):
    """追踪结果"""
    function_info: FunctionInfo
    code_map: List[CodeContext] = []
    audit_results: List['AuditResult'] = []  # 漏洞审计结果
    exploit_results: List['ExploitResult'] = []  # 漏洞利用结果


class AuditResult(BaseModel):
    """漏洞审计结果"""
    vulnerability_type: str  # 漏洞类型，如 "command_injection", "sql_injection"
    is_vulnerable: bool  # 是否存在漏洞
    confidence: str  # 置信度：high, medium, low
    description: str  # 漏洞描述
    taint_flow: Optional[str] = None  # 污点流向
    recommendation: Optional[str] = None  # 修复建议
    code_map: List[CodeContext] = []  # 相关代码上下文


class ExploitResult(BaseModel):
    """漏洞利用结果"""
    vulnerability_type: str  # 漏洞类型
    success: bool  # 是否利用成功
    poc_command: str  # PoC 命令
    output: str  # 执行输出
    error: Optional[str] = None  # 错误信息
