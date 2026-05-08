#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LangGraph Studio entrypoint for the trace audit workflow."""

from __future__ import annotations

from agents.trace_agent import TraceAgent
from agents.trace_workflow import TraceWorkflow
from config import get_config


def build_graph():
    """Build the graph loaded by `langgraph dev` / LangGraph Studio."""
    config = get_config()
    trace_agent = TraceAgent(
        project_path=config.project_path,
        debug=config.debug,
        output_dir=config.output_dir,
    )
    return TraceWorkflow(trace_agent, use_checkpointer=False).graph


graph = build_graph()
