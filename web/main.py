#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Web 应用入口
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.api.routes import router
from web.models import (  # 添加 web.models 的显式导入
    ProjectConfig, ScanRequest, AuditRequest,
    ScanResult, AuditResponse, TaskStatus
)
from web import database as db

# 创建 FastAPI 应用
app = FastAPI(
    title="代码安全审计系统 API",
    description="提供代码安全审计相关的 REST API",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    try:
        db.init_db()
        print("数据库初始化成功")
    except Exception as e:
        print(f"数据库初始化失败: {str(e)}")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 注册 API 路由
app.include_router(router)

# 静态文件和模板
templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

# 创建模板目录（如果不存在）
templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)

# 挂载静态文件（根路径，支持 HTML 和静态文件）
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/", response_class=FileResponse)
async def read_index():
    """返回 HTML 模板"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "欢迎使用代码安全审计系统"}


@app.get("/api")
async def api_docs():
    """API 文档重定向"""
    return {"message": "API 文档见 /docs"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "Code Audit API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
