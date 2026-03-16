#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计服务 - 负责执行代码审计
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any

# 添加项目根目录到路径（用于导入 agents 和 scan）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 添加 web 目录到路径（用于导入 web/models.py）
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    TraceResult, AuditResult, ExploitResult, CodeContext,
    AuditResponse
)


class AuditService:
    """审计服务"""

    def __init__(self, project_path: str, scan_path: str = "scan.py", max_turns: int = 50):
        self.project_path = project_path
        self.scan_path = scan_path
        self.max_turns = max_turns

    def audit_all(self) -> AuditResponse:
        """
        执行完整审计流程

        Returns:
            AuditResponse 审计响应
        """
        from agents.trace_agent import TraceAgent

        abs_project_path = os.path.abspath(self.project_path)

        agent = TraceAgent(
            project_path=abs_project_path,
            debug=False,
        )

        # 执行审计
        trace_results = agent.audit_all(scan_path=self.scan_path, code_path=abs_project_path)

        # 转换为 Pydantic 模型
        results = []
        for tr in trace_results:
            audit_results = []
            for ar in tr.audit_results:
                audit_results.append(AuditResult(
                    vulnerability_type=ar.vulnerability_type,
                    is_vulnerable=ar.is_vulnerable,
                    confidence=ar.confidence,
                    description=ar.description,
                    taint_flow=ar.taint_flow,
                    recommendation=ar.recommendation,
                    code_map=[CodeContext(
                        function_name=ctx.function_name,
                        file_path=ctx.file_path,
                        line_start=ctx.line_start,
                        line_end=ctx.line_end,
                        code_snippet=ctx.code_snippet,
                        is_entry_point=ctx.is_entry_point,
                        taint_source=ctx.taint_source,
                        taint_path=ctx.taint_path,
                    ) for ctx in ar.code_map],
                ))

            exploit_results = []
            for er in tr.exploit_results:
                exploit_results.append(ExploitResult(
                    vulnerability_type=er.vulnerability_type,
                    success=er.success,
                    poc_command=er.poc_command,
                    output=er.output,
                    error=er.error,
                ))

            results.append(TraceResult(
                func_name=tr.function_info.func_name,
                file_path=tr.function_info.file_path,
                start_line=tr.function_info.start_line,
                end_line=tr.function_info.end_line,
                code_snippet=tr.function_info.code_snippet,
                code_map=[CodeContext(
                    function_name=ctx.function_name,
                    file_path=ctx.file_path,
                    line_start=ctx.line_start,
                    line_end=ctx.line_end,
                    code_snippet=ctx.code_snippet,
                    is_entry_point=ctx.is_entry_point,
                    taint_source=ctx.taint_source,
                    taint_path=ctx.taint_path,
                ) for ctx in tr.code_map],
                audit_results=audit_results,
                exploit_results=exploit_results,
            ))

        return AuditResponse(
            status="completed",
            total=len(results),
            results=results
        )

    def audit_function(self, func_name: str) -> Dict[str, Any]:
        """
        审计单个函数

        Args:
            func_name: 函数名

        Returns:
            审计结果字典
        """
        from agents.trace_agent import TraceAgent
        from scan import scan_directory

        abs_project_path = os.path.abspath(self.project_path)

        # 先扫描获取函数信息
        scan_path = Path(self.scan_path)
        import importlib.util
        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)

        results = scan_module.scan_directory(abs_project_path)
        func_info = None
        for r in results:
            if r.func_name == func_name:
                func_info = r
                break

        if not func_info:
            return {"error": f"未找到函数: {func_name}"}

        # 创建 Agent 并审计单个函数
        agent = TraceAgent(project_path=abs_project_path, debug=False)

        trace_result = agent.audit_single(func_info)

        # 转换结果
        result = TraceResult(
            func_name=trace_result.function_info.func_name,
            file_path=trace_result.function_info.file_path,
            start_line=trace_result.function_info.start_line,
            end_line=trace_result.function_info.end_line,
            code_snippet=trace_result.function_info.code_snippet,
            code_map=[CodeContext(
                function_name=ctx.function_name,
                file_path=ctx.file_path,
                line_start=ctx.line_start,
                line_end=ctx.line_end,
                code_snippet=ctx.code_snippet,
                is_entry_point=ctx.is_entry_point,
                taint_source=ctx.taint_source,
                taint_path=ctx.taint_path,
            ) for ctx in trace_result.code_map],
            audit_results=[
                AuditResult(
                    vulnerability_type=ar.vulnerability_type,
                    is_vulnerable=ar.is_vulnerable,
                    confidence=ar.confidence,
                    description=ar.description,
                    taint_flow=ar.taint_flow,
                    recommendation=ar.recommendation,
                    code_map=[CodeContext(
                        function_name=ctx.function_name,
                        file_path=ctx.file_path,
                        line_start=ctx.line_start,
                        line_end=ctx.line_end,
                        code_snippet=ctx.code_snippet,
                        is_entry_point=ctx.is_entry_point,
                        taint_source=ctx.taint_source,
                        taint_path=ctx.taint_path,
                    ) for ctx in ar.code_map],
                ) for ar in trace_result.audit_results
            ],
            exploit_results=[
                ExploitResult(
                    vulnerability_type=er.vulnerability_type,
                    success=er.success,
                    poc_command=er.poc_command,
                    output=er.output,
                    error=er.error,
                ) for er in trace_result.exploit_results
            ],
        )

        return {"status": "completed", "result": result.model_dump()}
