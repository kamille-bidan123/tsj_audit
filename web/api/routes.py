#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 路由 - 增加 SQLite 数据库支持和用户认证
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import uuid
from pathlib import Path

from web.models import (
    ProjectConfig, ScanRequest, AuditRequest,
    ScanResult, AuditResponse, TaskStatus
)
from web.services.scan_service import ScanService
from web.services.audit_service import AuditService
from web import database as db

router = APIRouter(prefix="/api", tags=["Audit API"])

# OAuth2 密码模式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


# ========== 认证依赖 ==========

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """获取当前登录用户"""
    # 优先从请求头的 Authorization 字段获取（支持 fetch 请求）
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            user_id = int(auth_header.replace("Bearer ", ""))
            return db.get_user_by_id(user_id)
        except Exception:
            pass

    # 兼容 Cookie 方式
    token = request.cookies.get("Authorization")
    if not token:
        return None
    try:
        user_id = int(token)
        return db.get_user_by_id(user_id)
    except Exception:
        return None


def require_auth(request: Request) -> Dict[str, Any]:
    """要求用户必须登录"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(request: Request) -> Dict[str, Any]:
    """要求用户必须是管理员"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="无管理员权限")
    return user


# ========== 初始化 ==========

@router.post("/init-db")
def initialize_database():
    """初始化数据库"""
    try:
        db.init_db()
        db.init_default_admin()
        return {"status": "success", "message": "数据库初始化完成"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库初始化失败: {str(e)}")


# ========== 认证相关 ==========

class LoginForm(BaseModel):
    """登录表单"""
    username: str
    password: str


class RegisterForm(BaseModel):
    """注册表单"""
    username: str
    password: str
    email: Optional[str] = None


class LoginResponse(BaseModel):
    """登录响应"""
    user_id: int
    username: str
    email: Optional[str] = None
    role: str
    token: str


@router.post("/register")
def register(form: RegisterForm):
    """
    用户注册

    - **username**: 用户名
    - **password**: 密码
    - **email**: 邮箱（可选）
    """
    try:
        # 检查用户是否已存在
        if db.get_user_by_username(form.username):
            raise HTTPException(status_code=400, detail="用户名已存在")

        user_id = db.create_user(form.username, form.password, form.email)
        if not user_id:
            raise HTTPException(status_code=400, detail="注册失败")

        return {
            "status": "success",
            "message": "注册成功",
            "data": {
                "user_id": user_id,
                "username": form.username
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


@router.post("/login")
def login(form: LoginForm, request: Request):
    """
    用户登录

    - **username**: 用户名
    - **password**: 密码
    """
    try:
        user = db.authenticate_user(form.username, form.password)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 设置 cookie
        response = {
            "status": "success",
            "data": {
                "user_id": user['id'],
                "username": user['username'],
                "email": user.get('email'),
                "role": user.get('role', 'user')
            }
        }
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")


@router.post("/logout")
def logout(request: Request):
    """用户登出"""
    response = {"status": "success", "message": "已登出"}
    return response


@router.get("/user")
def get_current_user_info(user: Dict[str, Any] = Depends(require_auth)):
    """获取当前用户信息"""
    return {
        "status": "success",
        "data": {
            "user_id": user['id'],
            "username": user['username'],
            "email": user.get('email'),
            "role": user.get('role', 'user'),
            "is_active": user.get('is_active', 1) == 1
        }
    }


# ========== 用户管理 ==========

@router.get("/users")
def list_users(role: Optional[str] = None, user: Dict[str, Any] = Depends(require_admin)):
    """
    列出用户（仅管理员）

    - **role**: 用户角色过滤（可选）
    """
    try:
        users = db.list_users(role)
        return {
            "status": "success",
            "data": {
                "users": users,
                "total": len(users)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户列表失败: {str(e)}")


@router.post("/users")
def create_user(
    form: RegisterForm,
    user: Dict[str, Any] = Depends(require_admin)
):
    """
    创建用户（仅管理员）

    - **username**: 用户名
    - **password**: 密码
    - **email**: 邮箱（可选）
    """
    try:
        # 检查用户是否已存在
        if db.get_user_by_username(form.username):
            raise HTTPException(status_code=400, detail="用户名已存在")

        user_id = db.create_user(form.username, form.password, form.email)
        if not user_id:
            raise HTTPException(status_code=400, detail="创建用户失败")

        return {
            "status": "success",
            "message": "用户创建成功",
            "data": {
                "user_id": user_id,
                "username": form.username
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建用户失败: {str(e)}")


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    email: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_admin)
):
    """
    更新用户信息（仅管理员）

    - **user_id**: 用户 ID
    - **email**: 邮箱（可选）
    - **role**: 角色（可选）
    - **is_active**: 是否激活（可选）
    - **password**: 新密码（可选）
    """
    try:
        # 检查用户是否存在
        existing = db.get_user_by_id(user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 不能修改自己的管理员权限（防止权限丢失）
        if user.get('id') == user_id and role and role != existing.get('role'):
            raise HTTPException(status_code=400, detail="不能修改自己的管理员权限")

        update_data = {}
        if email is not None:
            update_data['email'] = email
        if role is not None:
            update_data['role'] = role
        if is_active is not None:
            update_data['is_active'] = 1 if is_active else 0
        if password is not None:
            update_data['password'] = password

        if db.update_user(user_id, **update_data):
            return {
                "status": "success",
                "message": "用户信息更新成功"
            }
        else:
            raise HTTPException(status_code=400, detail="用户信息未更新")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新用户失败: {str(e)}")


@router.delete("/users/{user_id}")
def delete_user(user_id: int, user: Dict[str, Any] = Depends(require_admin)):
    """
    删除用户（仅管理员）

    - **user_id**: 用户 ID
    """
    try:
        # 不能删除自己
        if user.get('id') == user_id:
            raise HTTPException(status_code=400, detail="不能删除自己")

        # 不能删除默认管理员
        existing = db.get_user_by_id(user_id)
        if existing and existing.get('username') == 'admin':
            raise HTTPException(status_code=400, detail="不能删除默认管理员")

        if db.delete_user(user_id):
            return {
                "status": "success",
                "message": "用户已删除"
            }
        else:
            raise HTTPException(status_code=404, detail="用户不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除用户失败: {str(e)}")


# ========== 健康检查 ==========

@router.get("/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "service": "Code Audit API"}


# ========== 扫描相关 ==========

@router.post("/scan")
def scan_project(request: ScanRequest):
    """
    扫描项目中的 URL 路由

    - **project_path**: 项目路径
    - **scan_path**: 扫描脚本路径（默认 scan.py）
    """
    try:
        # 保存项目信息
        db.save_project(request.project_path, "c")

        # 执行扫描
        service = ScanService(
            project_path=request.project_path,
            scan_path=request.scan_path or "scan.py"
        )
        result = service.scan()

        # 保存扫描结果
        task_id = str(uuid.uuid4())
        db.save_scan_results(task_id, result.urls)

        return {
            "status": "success",
            "task_id": task_id,
            "data": result.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit")
def audit_project(request: AuditRequest, background_tasks: BackgroundTasks):
    """
    执行完整审计

    - **project_path**: 项目路径
    - **scan_path**: 扫描脚本路径（默认 scan.py）
    - **max_turns**: 审计最大轮数（默认 50）
    """
    try:
        # 保存项目信息
        db.save_project(request.project_path, "c")

        # 创建审计任务
        task_id = str(uuid.uuid4())
        db.create_audit_task(task_id, request.project_path, request.scan_path or "scan.py", request.max_turns)

        service = AuditService(
            project_path=request.project_path,
            scan_path=request.scan_path or "scan.py",
            max_turns=request.max_turns
        )
        result = service.audit_all()

        # 保存结果到数据库
        for trace_result in result.results:
            db.save_trace_result(task_id, trace_result)

        # 更新任务状态
        db.update_audit_task_status(task_id, "completed", len(result.results))

        return {
            "status": "success",
            "task_id": task_id,
            "data": result.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/{func_name}")
def audit_single_function(func_name: str, project_path: str, scan_path: Optional[str] = "scan.py"):
    """
    审计单个函数

    - **func_name**: 函数名
    - **project_path**: 项目路径
    - **scan_path**: 扫描脚本路径
    """
    try:
        # 保存项目信息
        db.save_project(project_path, "c")

        service = AuditService(project_path=project_path, scan_path=scan_path)
        result = service.audit_function(func_name)

        # 保存到数据库
        task_id = str(uuid.uuid4())
        db.create_audit_task(task_id, project_path, scan_path, 50)

        # 创建 TraceResult 对象
        trace_result = db.TraceResult(
            func_name=func_name,
            file_path=result.get("file_path", "*"),
            start_line=0,
            end_line=0,
            code_snippet=result.get("code_snippet", ""),
            audit_results=[],
            exploit_results=[]
        )

        # 填充审计结果
        if "results" in result:
            for r in result["results"]:
                audit_result = db.AuditResult(
                    vulnerability_type=r.get("vulnerability_type", ""),
                    is_vulnerable=r.get("is_vulnerable", False),
                    confidence=r.get("confidence", ""),
                    description=r.get("description", ""),
                    taint_flow=r.get("taint_flow"),
                    recommendation=r.get("recommendation")
                )
                trace_result.audit_results.append(audit_result)

        db.save_trace_result(task_id, trace_result)
        db.update_audit_task_status(task_id, "completed", 1)

        return {
            "status": "success",
            "task_id": task_id,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 结果查询 ==========

@router.get("/results")
def list_results(
    project_path: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """
    列出审计结果

    - **project_path**: 项目路径（可选）
    - **limit**: 每页数量
    - **offset**: 偏移量
    """
    try:
        if project_path:
            tasks = db.list_audit_tasks(project_path, limit)
        else:
            tasks = db.list_audit_tasks(None, limit)

        results = []
        for task in tasks:
            traces = db.get_trace_results(task["task_id"])
            results.append({
                "task": task,
                "traces": traces
            })

        return {
            "status": "success",
            "data": {
                "results": results,
                "total": len(results)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{task_id}")
def get_task_results(task_id: str):
    """
    获取任务的所有结果

    - **task_id**: 任务ID
    """
    try:
        task = db.get_audit_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        traces = db.get_trace_results(task_id)

        return {
            "status": "success",
            "data": {
                "task": task,
                "traces": traces
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trace/{trace_id}")
def get_trace_result(trace_id: int):
    """
    获取单个 Trace 结果

    - **trace_id**: Trace ID
    """
    try:
        result = db.get_trace_result_by_id(trace_id)
        if not result:
            raise HTTPException(status_code=404, detail="结果不存在")

        return {
            "status": "success",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 项目相关 ==========

class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    project_name: str
    project_path: str
    project_type: Optional[str] = "c"


@router.get("/projects")
def list_projects(user: Dict[str, Any] = Depends(require_auth), limit: int = 10):
    """
    列出用户项目

    - **limit**: 数量限制
    """
    try:
        projects = db.list_projects(user.get('id'), limit)
        return {
            "status": "success",
            "data": {
                "projects": projects,
                "total": len(projects)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects")
def create_project(
    form: CreateProjectRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    创建新项目

    - **project_name**: 项目名称
    - **project_path**: 项目路径
    - **project_type**: 项目类型（默认 c）
    """
    try:
        project_id = db.save_project(
            user.get('id'),
            form.project_name,
            form.project_path,
            form.project_type or "c"
        )
        if not project_id:
            raise HTTPException(status_code=400, detail="创建项目失败")

        return {
            "status": "success",
            "message": "项目创建成功",
            "data": {
                "id": project_id,
                "project_name": form.project_name,
                "project_path": form.project_path
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除项目

    - **project_id**: 项目 ID
    """
    try:
        project = db.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        if project.get('user_id') != user.get('id'):
            raise HTTPException(status_code=403, detail="无权限删除该项目")

        if db.delete_project(project_id, user.get('id')):
            return {
                "status": "success",
                "message": "项目已删除"
            }
        else:
            raise HTTPException(status_code=400, detail="删除项目失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除项目失败: {str(e)}")


@router.get("/projects/{project_path}")
def get_project(project_path: str):
    """
    获取项目详情

    - **project_path**: 项目路径
    """
    try:
        project = db.get_project(project_path)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

        return {
            "status": "success",
            "data": project
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 统计信息 ==========

@router.get("/stats")
def get_stats():
    """获取系统统计信息"""
    try:
        stats = db.get_stats()
        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 批量操作 ==========

@router.post("/audit/bulk")
def audit_multiple_projects(configs: List[ProjectConfig]):
    """
    批量审计多个项目

    - **configs**: 项目配置列表
    """
    results = []
    for config in configs:
        try:
            # 保存项目信息
            db.save_project(config.project_path, config.project_type or "c")

            service = AuditService(
                project_path=config.project_path,
                scan_path=config.scan_path or "scan.py"
            )
            result = service.audit_all()

            # 保存结果到数据库
            task_id = str(uuid.uuid4())
            db.create_audit_task(task_id, config.project_path, config.scan_path or "scan.py", 50)

            for trace_result in result.results:
                db.save_trace_result(task_id, trace_result)

            db.update_audit_task_status(task_id, "completed", len(result.results))

            results.append({
                "project_path": config.project_path,
                "status": "success",
                "task_id": task_id,
                "data": result.model_dump()
            })
        except Exception as e:
            results.append({
                "project_path": config.project_path,
                "status": "error",
                "error": str(e)
            })

    return {
        "status": "success",
        "total": len(results),
        "results": results
    }
