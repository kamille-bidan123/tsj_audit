#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trace Agent - 代码污点追踪审计 Agent

探索阶段：多轮对话，使用工具探索代码，最后输出 codemap
"""

import sys
import json
import importlib.util
from typing import List, Dict, Optional, Union
from pathlib import Path
from datetime import datetime
# 导入共享模型
from models import EntrySpec, FunctionInfo, CodeContext, TraceResult, AuditResult
from utils.export_utils import merge_checkpoints_and_export
from utils.path_utils import normalize_function_info_file_path, normalize_trace_results_file_paths


class TraceAgent:
    """
    污点追踪审计 Agent

    探索阶段：多轮对话 + 工具调用探索代码，最后输出 codemap
    审计阶段：基于 codemap 调用 sub-agent 进行漏洞审计
    """

    def __init__(
        self,
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
        # TUI 回调
        on_functions_loaded: callable = None,
        on_function_start: callable = None,
        on_function_complete: callable = None,
        on_function_restored: callable = None,
        on_log: callable = None,
    ):
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

        # TUI 回调
        self.on_functions_loaded = on_functions_loaded or (lambda x: None)
        self.on_function_start = on_function_start or (lambda x: None)
        self.on_function_complete = on_function_complete or (lambda x: None)
        self.on_function_restored = on_function_restored or (lambda x: None)
        self.on_log = on_log or (lambda x: None)

        self._input_knowledge: Optional[str] = None
        self._scan_results: Optional[List[Union[EntrySpec, FunctionInfo]]] = None

    def _log(self, message: str) -> None:
        """输出日志到 stderr 和 TUI"""
        print(message, file=sys.stderr, flush=True)
        self.on_log(message)

    def _get_checkpoint_dir(self, output_dir: str) -> Path:
        """获取中间信息保存目录"""
        return Path(output_dir) / "checkpoints"

    def _get_checkpoint_file(self, output_dir: str, func_name: str) -> Path:
        """获取单个函数的检查点文件路径"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)
        # 清理函数名中的非法字符
        safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in func_name)
        return checkpoint_dir / f"{safe_name}.json"

    def _save_checkpoint(self, output_dir: str, result: TraceResult):
        """保存审计检查点"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_file = self._get_checkpoint_file(output_dir, result.function_info.func_name)
        saved_result = normalize_trace_results_file_paths([result], None)[0]
        data = saved_result.model_dump()

        # 添加元信息
        data["_checkpoint_meta"] = {
            "saved_at": datetime.now().isoformat(),
            "func_name": saved_result.function_info.func_name,
            "file_path": saved_result.function_info.file_path,
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [检查点] 已保存: {checkpoint_file}", file=sys.stderr)

    def _save_conversation_history(self, agent_name: str, func_info: FunctionInfo, messages: List[Dict]):
        """保存特定 agent 的对话历史"""
        if not hasattr(self, 'output_dir') or not self.output_dir:
            return  # 如果没有设置输出目录，则不保存

        # 构建输出目录结构：output_dir/conversations/agent_name/function_name.json
        conversations_dir = Path(self.output_dir) / "conversations" / agent_name
        conversations_dir.mkdir(parents=True, exist_ok=True)

        # 清理函数名中的非法字符
        safe_func_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in func_info.func_name)

        conversation_file = conversations_dir / f"{safe_func_name}.json"
        saved_func_info = normalize_function_info_file_path(func_info, None)

        # 准备保存对话历史
        conversation_data = {
            "function_info": saved_func_info.model_dump(),
            "conversation_history": messages,
            "saved_at": datetime.now().isoformat(),
            "agent": agent_name
        }

        with open(conversation_file, "w", encoding="utf-8") as f:
            json.dump(conversation_data, f, indent=2, ensure_ascii=False)

        if self.debug:
            print(f"  [对话历史] {agent_name} 已保存: {conversation_file}", file=sys.stderr)

    def _load_checkpoint(self, output_dir: str, func_name: str) -> Optional[TraceResult]:
        """加载单个函数的审计检查点"""
        checkpoint_file = self._get_checkpoint_file(output_dir, func_name)

        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 移除元信息
            data.pop("_checkpoint_meta", None)

            result = TraceResult.model_validate(data)
            return result
        except Exception as e:
            if self.debug:
                print(f"  [警告] 加载检查点失败: {e}", file=sys.stderr)
            return None

    def _load_all_checkpoints(self, output_dir: str) -> Dict[str, TraceResult]:
        """加载所有审计检查点"""
        checkpoint_dir = self._get_checkpoint_dir(output_dir)

        if not checkpoint_dir.exists():
            return {}

        checkpoints = {}
        for checkpoint_file in checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                meta = data.pop("_checkpoint_meta", None)
                if meta:
                    func_name = meta.get("func_name", checkpoint_file.stem)
                    checkpoints[func_name] = TraceResult.model_validate(data)
            except Exception as e:
                if self.debug:
                    print(f"  [警告] 加载检查点失败 ({checkpoint_file}): {e}", file=sys.stderr)

        return checkpoints

    def load_entry_results(self, entry_path: str, code_path: Optional[str] = None) -> List[EntrySpec]:
        """加载 EntrySpec JSON 入口结果。"""
        if code_path is None:
            code_path = self.project_path

        path = Path(entry_path)

        if not path.exists():
            raise FileNotFoundError(f"未找到 EntrySpec JSON 文件: {path}")
        if path.suffix.lower() != ".json":
            raise ValueError(f"--entry 只接受 JSON 文件: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, list):
            raise ValueError(f"JSON 文件内容不是列表格式: {path}")

        results: list[EntrySpec] = []
        for idx, item in enumerate(raw_data):
            if isinstance(item, dict):
                try:
                    results.append(EntrySpec(**item))
                except Exception as e:
                    raise ValueError(f"JSON 文件中第 {idx+1} 项不是有效的 EntrySpec: {str(e)}")
            elif isinstance(item, EntrySpec):
                results.append(item)
            else:
                raise ValueError(f"JSON 文件中第 {idx+1} 项既不是字典也不是 EntrySpec 对象")

        self._scan_results = results
        return results

    def load_scan_results(self, scan_path: str, code_path: Optional[str] = None) -> List[EntrySpec]:
        """执行扫描脚本并加载 EntrySpec 结果。"""
        if code_path is None:
            code_path = self.project_path

        scan_path = Path(scan_path)

        if not scan_path.exists():
            raise FileNotFoundError(f"未找到 scan.py: {scan_path}")
        if scan_path.suffix.lower() == ".json":
            raise ValueError("--scan 只接受扫描脚本；JSON 入口请使用 --entry")

        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)

        if self.debug:
            print(
                f"[TraceAgent] 执行扫描：{scan_path} {code_path}", file=sys.stderr)

        raw_results = scan_module.scan_directory(code_path)
        results: list[EntrySpec] = []
        for idx, item in enumerate(raw_results):
            if isinstance(item, dict):
                try:
                    results.append(EntrySpec(**item))
                except Exception as e:
                    raise ValueError(f"扫描脚本返回第 {idx+1} 项不是有效的 EntrySpec: {str(e)}")
            elif isinstance(item, EntrySpec):
                results.append(item)
            else:
                raise ValueError(f"扫描脚本返回第 {idx+1} 项不是 EntrySpec")

        self._scan_results = results
        return results

    def audit_function(
        self,
        func_info: Union[EntrySpec, FunctionInfo],
    ) -> TraceResult:
        """
        审计单个函数

        Args:
            func_info: 接口函数信息
        Returns:
            TraceResult 追踪结果
        """
        from agents.runtime_factory import create_trace_explorer

        hydrated_func_info, code_logic, code_map, messages = create_trace_explorer(self).run(func_info)
        audit_results, exploit_results = self._audit_codemap(hydrated_func_info, code_map)
        self._save_conversation_history("trace_agent", hydrated_func_info, messages)

        return TraceResult(
            function_info=hydrated_func_info,
            code_logic=code_logic,
            code_map=code_map,
            audit_results=audit_results,
            exploit_results=exploit_results,
        )

    def _audit_codemap(
        self,
        func_info: FunctionInfo,
        code_map: List[CodeContext],
    ) -> tuple[List[AuditResult], list]:
        """基于 codemap 调用漏洞审计阶段。"""
        # 直接进入审计阶段，不需要额外的消息
        if self.debug:
            print(f"\n[审计阶段] 启动 AuditAgent 运行所有审计类型", file=sys.stderr)

        # 调用 AuditAgent 进行审计（自动运行所有审计类型）
        from agents.audit_agent import AuditAgent
        audit_agent = AuditAgent(
            function_info=func_info,
            code_map=code_map,
            project_path=self.project_path,
            debug=self.debug,
            output_dir=self.output_dir,
            on_log=self.on_log,
        )

        audit_results, exploit_results = audit_agent.audit()

        vulnerable_count = sum(1 for ar in audit_results if ar.is_vulnerable)
        self._log(f"[审计结果] 总计发现 {vulnerable_count} 个潜在漏洞，记录 {len(audit_results)} 条审计结果")
        for ar in audit_results:
            title = f" / {ar.title}" if ar.title else ""
            self._log(f"  - {ar.vulnerability_type}{title}: {ar.is_vulnerable} (置信度: {ar.confidence})")

        return audit_results, exploit_results

    def audit_all(
        self,
        scan_path: Optional[str] = None,
        entry_path: Optional[str] = None,
        code_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        resume: bool = False,
    ) -> None:
        """
        审计所有接口函数

        Args:
            code_path: 代码目录路径
            output_dir: 输出目录路径，用于保存中间检查点
            resume: 是否从中间断点恢复审计

        说明:
            审计结果会逐个保存到 output_dir/checkpoints/ 目录，
            完成后会自动合并所有 checkpoint 生成最终报告。
        """
        # 设置输出目录，以便后续保存对话历史
        self.output_dir = output_dir

        if bool(scan_path) == bool(entry_path):
            raise ValueError("必须且只能指定 scan_path 或 entry_path 之一")

        # 加载入口结果
        scan_results = (
            self.load_scan_results(scan_path, code_path)
            if scan_path
            else self.load_entry_results(entry_path, code_path)
        )
        self.on_functions_loaded(scan_results)

        self._log(f"[TraceAgent] 找到 {len(scan_results)} 个接口函数")

        # 如果启用了resume模式，加载已有的检查点
        checkpoints = {}
        completed_funcs = set()
        if self.debug:
            print(f"[DEBUG] resume={resume}, output_dir={output_dir}", file=sys.stderr)
        if resume and output_dir:
            if self.debug:
                print(f"[DEBUG] 正在加载检查点...", file=sys.stderr)
            checkpoints = self._load_all_checkpoints(output_dir)
            completed_funcs = set(checkpoints.keys())
            if self.debug:
                print(f"[DEBUG] 加载了 {len(checkpoints)} 个检查点", file=sys.stderr)
            if completed_funcs:
                print(f"\n[TraceAgent] 从检查点恢复: 找到 {len(completed_funcs)} 个已完成的函数", file=sys.stderr)
                print(f"[TraceAgent] 已完成的函数列表: {list(completed_funcs)}", file=sys.stderr)
                for func_info in scan_results:
                    checkpoint = checkpoints.get(func_info.func_name)
                    if checkpoint:
                        self.on_function_restored(checkpoint.function_info)

        # 逐个审计
        for func_info in scan_results:
            func_name = func_info.func_name

            # 检查是否已完成
            if func_name in completed_funcs:
                if self.debug:
                    print(f"\n[跳过] {func_name} (已完成，来自检查点)", file=sys.stderr)
                continue

            # 新审计未完成的函数
            entry_line = func_info.start_line if getattr(func_info, "start_line", None) is not None else "?"
            self._log(f"[TraceAgent] 开始函数：{func_name} @ {func_info.file_path}:{entry_line}")

            # 通知开始审计
            self.on_function_start(func_info)

            result = self.audit_function(func_info)

            # 通知完成审计
            self.on_function_complete(result.function_info)
            self._log(f"[TraceAgent] 完成函数：{func_name}")

            # 保存检查点
            if output_dir:
                self._save_checkpoint(output_dir, result)

        # 合并所有 checkpoint 生成最终报告
        if output_dir:
            self._log(f"[导出] 合并 checkpoint 并生成报告: {output_dir}")
            merge_checkpoints_and_export(output_dir, debug=self.debug)

    def audit_single(
        self,
        func_info,
    ) -> 'TraceResult':
        """
        审计单个函数

        Args:
            func_info: 接口函数信息

        Returns:
            TraceResult 追踪结果
        """
        return self.audit_function(func_info)
