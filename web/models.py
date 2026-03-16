#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web 服务数据模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ========== 项目相关 ==========
class ProjectConfig(BaseModel):
    """项目配置"""
    project_path: str
    project_type: str = "c"
    attack_surface: str = "civetweb"
    scan_path: str = "scan.py"


class ScanRequest(BaseModel):
    """扫描请求"""
    project_path: str
    scan_path: Optional[str] = "scan.py"


class AuditRequest(BaseModel):
    """审计请求"""
    project_path: str
    scan_path: Optional[str] = "scan.py"
    max_turns: int = 50


# ========== 扫描结果 ==========
class ScanUrlInfo(BaseModel):
    """扫描到的 URL 信息"""
    url_path: str
    callback_func: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str


class ScanResult(BaseModel):
    """扫描结果"""
    total: int
    urls: List[ScanUrlInfo]


# ========== 审计相关 ==========
class CodeContext(BaseModel):
    """代码上下文"""
    function_name: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    is_entry_point: bool = False
    taint_source: Optional[str] = None
    taint_path: Optional[str] = None


class AuditResult(BaseModel):
    """漏洞审计结果"""
    vulnerability_type: str
    is_vulnerable: bool
    confidence: str
    description: str
    taint_flow: Optional[str] = None
    recommendation: Optional[str] = None
    code_map: List[CodeContext] = []


class ExploitResult(BaseModel):
    """漏洞利用结果"""
    vulnerability_type: str
    success: bool
    poc_command: str
    output: str
    error: Optional[str] = None


class TraceResult(BaseModel):
    """追踪结果"""
    func_name: str
    file_path: str
    start_line: int
    end_line: int
    code_snippet: str
    code_map: List[CodeContext] = []
    audit_results: List[AuditResult] = []
    exploit_results: List[ExploitResult] = []


class AuditResponse(BaseModel):
    """审计响应"""
    status: str
    total: int
    results: List[TraceResult]


# ========== 任务状态 ==========
class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class TaskQuery(BaseModel):
    """任务查询"""
    task_id: str
