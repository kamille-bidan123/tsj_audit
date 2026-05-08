#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph workflow for a single trace audit.

The graph owns the phase transitions for one FunctionInfo:
explore -> codemap -> audit -> result.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from agents.deepagents_trace_explorer import DeepAgentsTraceExplorer
from models import AuditResult, CodeContext, ExploitResult, FunctionInfo, TraceResult


class TraceWorkflowState(TypedDict, total=False):
    """Serializable graph state for one function audit."""

    function_info: Dict[str, Any]
    messages: List[Dict[str, Any]]
    code_logic: str
    code_map: List[Dict[str, Any]]
    audit_results: List[Dict[str, Any]]
    exploit_results: List[Dict[str, Any]]
    trace_result: Dict[str, Any]


def _safe_thread_id(func_name: str) -> str:
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in func_name)
    return f"trace:{safe_name}"


def _load_langgraph():
    """Import LangGraph lazily so module imports stay cheap and testable."""
    try:
        from langgraph.graph import END, START, StateGraph
        try:
            from langgraph.checkpoint.memory import InMemorySaver
        except ImportError:
            from langgraph.checkpoint.memory import MemorySaver as InMemorySaver
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is required for TraceWorkflow. Install project dependencies "
            "with `.venv/bin/pip3.14 install langgraph` or your package manager."
        ) from exc

    return START, END, StateGraph, InMemorySaver


class TraceWorkflow:
    """LangGraph-backed workflow wrapper around the existing TraceAgent steps."""

    def __init__(self, trace_agent, *, use_checkpointer: bool = True):
        self.trace_agent = trace_agent
        self.use_checkpointer = use_checkpointer
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            START, END, StateGraph, InMemorySaver = _load_langgraph()

            graph = StateGraph(TraceWorkflowState)
            graph.add_node("explore", self._explore)
            graph.add_node("codemap", self._codemap)
            graph.add_node("audit", self._audit)
            graph.add_node("result", self._result)

            graph.add_edge(START, "explore")
            graph.add_edge("explore", "codemap")
            graph.add_edge("codemap", "audit")
            graph.add_edge("audit", "result")
            graph.add_edge("result", END)

            if self.use_checkpointer:
                self._graph = graph.compile(checkpointer=InMemorySaver())
            else:
                self._graph = graph.compile()

        return self._graph

    def run(self, func_info: FunctionInfo) -> TraceResult:
        initial_state: TraceWorkflowState = {
            "function_info": func_info.model_dump(),
        }
        config = {"configurable": {"thread_id": _safe_thread_id(func_info.func_name)}}
        final_state = self.graph.invoke(initial_state, config=config)
        return TraceResult.model_validate(final_state["trace_result"])

    def _explore(self, state: TraceWorkflowState) -> TraceWorkflowState:
        func_info = FunctionInfo.model_validate(state["function_info"])
        code_logic, code_map, messages = DeepAgentsTraceExplorer(self.trace_agent).run(func_info)
        return {
            "messages": messages,
            "code_logic": code_logic,
            "code_map": [ctx.model_dump() for ctx in code_map],
        }

    def _codemap(self, state: TraceWorkflowState) -> TraceWorkflowState:
        return {
            "messages": state.get("messages", []),
            "code_logic": state.get("code_logic", ""),
            "code_map": state.get("code_map", []),
        }

    def _audit(self, state: TraceWorkflowState) -> TraceWorkflowState:
        func_info = FunctionInfo.model_validate(state["function_info"])
        code_map = [
            ctx if isinstance(ctx, CodeContext) else CodeContext.model_validate(ctx)
            for ctx in state.get("code_map", [])
        ]
        audit_results, exploit_results = self.trace_agent._audit_codemap(func_info, code_map)
        return {
            "audit_results": [result.model_dump() for result in audit_results],
            "exploit_results": [result.model_dump() for result in exploit_results],
        }

    def _result(self, state: TraceWorkflowState) -> TraceWorkflowState:
        func_info = FunctionInfo.model_validate(state["function_info"])
        code_map = [CodeContext.model_validate(ctx) for ctx in state.get("code_map", [])]
        audit_results = [
            AuditResult.model_validate(result)
            for result in state.get("audit_results", [])
        ]
        exploit_results = [
            ExploitResult.model_validate(result)
            for result in state.get("exploit_results", [])
        ]

        result = TraceResult(
            function_info=func_info,
            code_logic=state.get("code_logic", ""),
            code_map=code_map,
            audit_results=audit_results,
            exploit_results=exploit_results,
        )

        self.trace_agent._save_conversation_history(
            "trace_agent",
            func_info,
            state.get("messages", []),
        )

        return {"trace_result": result.model_dump()}
