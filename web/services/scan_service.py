#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描服务 - 负责扫描代码中的 URL 路由
"""

import sys
import os
import importlib.util
from pathlib import Path
from typing import List, Dict


class ScanService:
    """扫描服务"""

    def __init__(self, project_path: str, scan_path: str = "scan.py"):
        self.project_path = project_path
        self.scan_path = scan_path

    def _load_scan_module(self):
        """动态加载 scan.py 模块"""
        scan_path = Path(self.scan_path)
        if not scan_path.exists():
            raise FileNotFoundError(f"未找到 scan.py: {scan_path}")

        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)
        return scan_module

    def scan(self):
        """
        执行扫描

        Returns:
            ScanResult 扫描结果
        """
        # 获取绝对路径
        abs_project_path = os.path.abspath(self.project_path)

        # 动态加载 scan.py 模块
        scan_module = self._load_scan_module()

        # 执行扫描
        results = scan_module.scan_directory(abs_project_path)

        # 使用 web/models.py 中的模型
        from web.models import ScanUrlInfo, ScanResult

        scan_urls = []
        for r in results:
            scan_urls.append(ScanUrlInfo(
                url_path="",  # scan.py 中没有直接返回 url_path
                callback_func=r.func_name,
                file_path=r.file_path,
                start_line=r.start_line,
                end_line=r.end_line,
                code_snippet=r.code_snippet,
            ))

        return ScanResult(
            total=len(scan_urls),
            urls=scan_urls
        )

    def scan_with_full_details(self) -> List[Dict]:
        """
        执行扫描并返回详细信息

        Returns:
            包含详细信息的字典列表
        """
        abs_project_path = os.path.abspath(self.project_path)

        scan_module = self._load_scan_module()
        results = scan_module.scan_directory(abs_project_path)

        # 转换为字典列表
        details = []
        for r in results:
            details.append({
                "func_name": r.func_name,
                "file_path": r.file_path,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "code_snippet": r.code_snippet,
                "input": r.input,  # 外部输入点说明
            })

        return details
