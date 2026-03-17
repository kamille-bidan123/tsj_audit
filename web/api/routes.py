#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 路由 - 增加 SQLite 数据库支持和用户认证
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends, File, UploadFile, Body
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json
import os
import uuid
import sqlite3
import zipfile
import shutil
import re
from pathlib import Path
import tarfile
from datetime import datetime

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


# ========== Skills 相关 ==========

class CreateSkillRequest(BaseModel):
    """创建 skill 请求"""
    skill_name: str
    description: Optional[str] = None
    is_public: Optional[bool] = False


class UpdateSkillRequest(BaseModel):
    """更新 skill 请求"""
    description: Optional[str] = None
    is_public: Optional[bool] = None


@router.get("/skills")
def list_skills(user: Dict[str, Any] = Depends(require_auth),PublicOnly: Optional[bool] = False, limit: int = 50):
    """
    列出用户 skills 或公开 skills

    - **publicOnly**: 是否只获取公开 skills
    - **limit**: 数量限制
    """
    try:
        if PublicOnly:
            skills = db.list_public_skills(limit)
        else:
            skills = db.list_skills(user.get('id'), limit)
        return {
            "status": "success",
            "data": {
                "skills": skills,
                "total": len(skills)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills")
def create_skill(
    form: CreateSkillRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    创建新 skill

    - **skill_name**: Skill 名称
    - **description**: 描述（可选）
    - **is_public**: 是否公开（默认 false）
    """
    try:
        # 检查 skill 是否已存在
        if db.get_skill_by_name(form.skill_name):
            raise HTTPException(status_code=400, detail="Skill 名称已存在")

        # 生成 skill 存储路径
        skill_dir = f"skills/{user.get('id')}/{form.skill_name}"
        skill_path = f"/data/{skill_dir}"

        skill_id = db.save_skill(
            user.get('id'),
            form.skill_name,
            skill_path,
            form.description,
            1 if form.is_public else 0
        )
        if not skill_id:
            raise HTTPException(status_code=400, detail="创建 skill 失败")

        return {
            "status": "success",
            "message": "Skill 创建成功",
            "data": {
                "id": skill_id,
                "skill_name": form.skill_name,
                "skill_path": skill_path
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建 skill 失败: {str(e)}")


@router.put("/skills/{skill_id}")
def update_skill(
    skill_id: int,
    form: UpdateSkillRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    更新 skill 信息

    - **skill_id**: Skill ID
    - **description**: 新描述（可选）
    - **is_public**: 是否公开（可选）
    """
    try:
        skill = db.get_skill_by_id(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill 不存在")

        if skill.get('user_id') != user.get('id'):
            raise HTTPException(status_code=403, detail="无权限修改该 Skill")

        update_data = {}
        if form.description is not None:
            update_data['description'] = form.description
        if form.is_public is not None:
            update_data['is_public'] = 1 if form.is_public else 0

        conn = sqlite3.connect(db.get_db_path(), check_same_thread=False)
        cursor = conn.cursor()
        fields = []
        values = []
        for key, value in update_data.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(skill_id)

        if fields:
            cursor.execute(f"UPDATE skills SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
            conn.commit()

        return {
            "status": "success",
            "message": "Skill 更新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新 skill 失败: {str(e)}")


@router.delete("/skills/{skill_id}")
def delete_skill(
    skill_id: int,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    删除 skill

    - **skill_id**: Skill ID
    """
    try:
        skill = db.get_skill_by_id(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill 不存在")

        if skill.get('user_id') != user.get('id'):
            raise HTTPException(status_code=403, detail="无权限删除该 Skill")

        # 删除数据库记录
        if db.delete_skill(skill_id, user.get('id')):
            # 删除物理文件
            skill_full_path = db.get_skill_full_path(skill_id)
            if skill_full_path and skill_full_path.exists():
                try:
                    shutil.rmtree(skill_full_path)
                except Exception:
                    pass
            return {
                "status": "success",
                "message": "Skill 已删除"
            }
        else:
            raise HTTPException(status_code=400, detail="删除 skill 失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除 skill 失败: {str(e)}")


# ========== Skill 文件上传 ==========

class UploadedSkillInfo(BaseModel):
    """上传的 Skill 信息"""
    skill_name: str
    description: Optional[str] = None
    file_name: str
    is_public: Optional[bool] = False


@router.post("/skills/upload")
async def upload_skill(
    request: Request,
    skill_file: UploadFile = File(...),
    description: Optional[str] = None,
    is_public: Optional[bool] = False,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    上传 Skill 文件（.zip 或 .md）

    - **skill_file**: Skill 压缩包（.zip）或 Markdown 文件（.md）
    - **description**: Skill 描述（可选）
    - **is_public**: 是否公开（默认 false）
    """
    try:
        # 验证文件类型
        filename = skill_file.filename or ""
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext not in ['.zip', '.md']:
            raise HTTPException(status_code=400, detail="只支持 .zip 或 .md 文件")

        # 创建 skills 目录
        skills_dir = db.get_skills_dir()
        user_skills_dir = skills_dir / str(user.get('id'))
        user_skills_dir.mkdir(parents=True, exist_ok=True)

        # 处理 .zip 文件
        if file_ext == '.zip':
            # 生成 skill 名称（从文件名提取）
            skill_name = os.path.splitext(filename)[0].lower()
            # 只允许小写字母、数字和连字符
            skill_name = re.sub(r'[^a-z0-9-]', '-', skill_name)
            skill_name = re.sub(r'-+', '-', skill_name).strip('-')

            if len(skill_name) < 2 or len(skill_name) > 64:
                raise HTTPException(status_code=400, detail="Skill 名称长度应在 2-64 个字符之间")

            # 检查 skill 是否已存在
            existing_skill = db.get_skill_by_name(skill_name)
            if existing_skill and existing_skill.get('user_id') == user.get('id'):
                raise HTTPException(status_code=400, detail=f"Skill '{skill_name}' 已存在")

            # 解压目录
            extract_dir = user_skills_dir / skill_name
            extract_dir.mkdir(parents=True, exist_ok=True)

            # 解压文件
            zip_path = user_skills_dir / f"{skill_name}.zip"
            with open(zip_path, "wb") as f:
                f.write(await skill_file.read())

            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # 验证压缩包结构
                    file_list = zip_ref.namelist()

                    # 检查是否包含 SKILL.md
                    skill_md_found = any('SKILL.md' in f or 'skill.md' in f.lower() for f in file_list)
                    if not skill_md_found:
                        # 自动创建 SKILL.md
                        pass

                    zip_ref.extractall(extract_dir)
            finally:
                # 清理临时 zip 文件
                if zip_path.exists():
                    zip_path.unlink()

            # 从 SKILL.md 提取信息
            skill_md_path = None
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower() == 'skill.md':
                        skill_md_path = Path(root) / f
                        break

            # 解析 SKILL.md 获取 name 和 description
            extracted_name = None
            extracted_description = None
            if skill_md_path and skill_md_path.exists():
                content = skill_md_path.read_text(encoding='utf-8')
                # 解析 YAML front matter
                if content.startswith('---'):
                    end_match = re.search(r'^---\n(.*?)\n^---', content, re.MULTILINE | re.DOTALL)
                    if end_match:
                        yaml_content = end_match.group(1)
                        # 简单解析 YAML
                        name_match = re.search(r'name:\s*(.+)', yaml_content)
                        if name_match:
                            extracted_name = name_match.group(1).strip()

                        desc_match = re.search(r'description:\s*(.+)', yaml_content)
                        if desc_match:
                            extracted_description = desc_match.group(1).strip()

            # 使用上传的 name 或从文件名提取的 name
            final_skill_name = skill_name

            # 保存到数据库
            skill_path = f"/skills/{user.get('id')}/{final_skill_name}"
            skill_id = db.save_skill(
                user.get('id'),
                final_skill_name,
                skill_path,
                description or extracted_description,
                1 if is_public else 0,
                filename
            )

            return {
                "status": "success",
                "message": "Skill 上传成功",
                "data": {
                    "id": skill_id,
                    "skill_name": final_skill_name,
                    "skill_path": skill_path
                }
            }

        # 处理 .md 文件
        elif file_ext == '.md':
            # 生成 skill 名称
            skill_name = os.path.splitext(filename)[0].lower()
            skill_name = re.sub(r'[^a-z0-9-]', '-', skill_name)
            skill_name = re.sub(r'-+', '-', skill_name).strip('-')

            if len(skill_name) < 2 or len(skill_name) > 64:
                raise HTTPException(status_code=400, detail="Skill 名称长度应在 2-64 个字符之间")

            # 检查 skill 是否已存在
            existing_skill = db.get_skill_by_name(skill_name)
            if existing_skill and existing_skill.get('user_id') == user.get('id'):
                raise HTTPException(status_code=400, detail=f"Skill '{skill_name}' 已存在")

            # 创建 skill 目录
            skill_dir = user_skills_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)

            # 保存 .md 文件
            md_path = skill_dir / "SKILL.md"
            content = await skill_file.read()
            md_path.write_text(content, encoding='utf-8')

            # 从 .md 文件提取信息
            extracted_name = None
            extracted_description = None
            if md_path.exists():
                file_content = md_path.read_text(encoding='utf-8')
                if file_content.startswith('---'):
                    end_match = re.search(r'^---\n(.*?)\n^---', file_content, re.MULTILINE | re.DOTALL)
                    if end_match:
                        yaml_content = end_match.group(1)
                        name_match = re.search(r'name:\s*(.+)', yaml_content)
                        if name_match:
                            extracted_name = name_match.group(1).strip()
                        desc_match = re.search(r'description:\s*(.+)', yaml_content)
                        if desc_match:
                            extracted_description = desc_match.group(1).strip()

            # 保存到数据库
            skill_path = f"/skills/{user.get('id')}/{skill_name}"
            skill_id = db.save_skill(
                user.get('id'),
                skill_name,
                skill_path,
                description or extracted_description,
                1 if is_public else 0,
                filename
            )

            return {
                "status": "success",
                "message": "Skill 上传成功",
                "data": {
                    "id": skill_id,
                    "skill_name": skill_name,
                    "skill_path": skill_path
                }
            }

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="无效的 ZIP 文件")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传 skill 失败: {str(e)}")


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


# ========== 审计任务管理（支持多阶段追踪） ==========

class AuditTaskResponse(BaseModel):
    """审计任务响应"""
    task_id: str
    status: str
    current_phase: str
    progress: int
    message: Optional[str] = None


async def run_audit_task(task_id: str, project_path: str, scan_path: str, max_turns: int, user_id: int):
    """
    异步运行审计任务（后台任务）
    使用 SSE 推送进度
    """
    from agents.trace_agent import TraceAgent
    from scan import scan_directory
    import importlib.util
    from pathlib import Path

    try:
        # 1. scan 阶段
        db.update_audit_task_phase(task_id, "scan", "running", 10)
        db.update_audit_task_status(task_id, "running")

        abs_project_path = os.path.abspath(project_path)
        scan_path_obj = Path(scan_path)

        spec = importlib.util.spec_from_file_location("scan_module", scan_path_obj)
        scan_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_module)

        scan_results = scan_module.scan_directory(abs_project_path)
        db.save_scan_results(task_id, scan_results)
        db.update_audit_task_phase(task_id, "scan", "completed", 20)
        db.append_conversation_log(task_id, None, "system", "Scan 阶段完成")

        # 2. trace 阶段
        db.update_audit_task_phase(task_id, "trace", "running", 30)

        agent = TraceAgent(project_path=abs_project_path, debug=False)
        total_funcs = len(scan_results)
        db.update_audit_task_status(task_id, "running", total_functions=total_funcs)

        trace_results_list = []
        for idx, func_info in enumerate(scan_results):
            current_func = func_info.func_name
            db.append_conversation_log(task_id, current_func, "system", f"开始审计: {current_func}")

            trace_result = agent.audit_function(func_info)
            trace_results_list.append(trace_result)

            db.save_trace_result(task_id, trace_result)
            db.increment_completed_functions(task_id)

            progress = 30 + (idx + 1) * 60 // total_funcs if total_funcs > 0 else 90
            db.update_audit_task_phase(task_id, "trace", "running", progress)
            db.append_conversation_log(task_id, current_func, "assistant", f"完成审计: {current_func}")

        db.update_audit_task_phase(task_id, "trace", "completed", 90)
        db.append_conversation_log(task_id, None, "system", "Trace 阶段完成")

        # 3. report 阶段
        db.update_audit_task_phase(task_id, "report", "running", 95)

        from agents.report_agent import ReportAgent
        report_agent = ReportAgent(project_path=abs_project_path)
        report_content = report_agent.generate_report(trace_results_list)

        db.append_conversation_log(task_id, None, "system", "报告生成完成")
        db.update_audit_task_phase(task_id, "report", "completed", 100)

        # 完成任务
        db.update_audit_task_status(task_id, "completed", total_functions=total_funcs)
        db.append_conversation_log(task_id, None, "assistant", "审计任务 completed")

    except Exception as e:
        import traceback
        error_msg = f"审计失败: {str(e)}\n{traceback.format_exc()}"
        db.append_conversation_log(task_id, None, "error", error_msg)
        db.update_audit_task_phase(task_id, "unknown", "failed", 0)


@router.post("/tasks/audit", response_model=AuditTaskResponse)
async def create_audit_task_endpoint(
    request: AuditRequest,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    创建审计任务（异步执行）

    - **project_path**: 项目路径
    - **scan_path**: 扫描脚本路径（默认 scan.py）
    - **max_turns**: 审计最大轮数（默认 50）
    """
    try:
        # 保存项目信息
        db.save_project(user.get('id'), "审计项目", request.project_path, "c")

        # 创建审计任务
        task_id = str(uuid.uuid4())
        db.create_audit_task(task_id, request.project_path, request.scan_path or "scan.py", request.max_turns)

        # 启动后台任务
        background_tasks.add_task(
            run_audit_task,
            task_id,
            request.project_path,
            request.scan_path or "scan.py",
            request.max_turns,
            user.get('id')
        )

        return {
            "task_id": task_id,
            "status": "pending",
            "current_phase": "scan",
            "progress": 0,
            "message": "任务已创建，正在排队执行"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """
    SSE 流式推送任务状态
    """
    async def event_stream():
        task = db.get_audit_task(task_id)
        if not task:
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'status', 'task': task})}\n\n"

        while True:
            task = db.get_audit_task(task_id)
            if not task:
                yield f"data: {json.dumps({'type': 'completed', 'message': 'Task not found'})}\n\n"
                break

            status = task.get('status', 'unknown')

            if status in ['completed', 'failed']:
                logs = db.get_conversation_logs(task_id)
                yield f"data: {json.dumps({'type': 'final', 'task': task, 'logs': logs})}\n\n"
                break

            logs = db.get_conversation_logs(task_id)
            if logs:
                for log in logs[-5:]:
                    yield f"data: {json.dumps({'type': 'message', 'log': log})}\n\n"

            yield f"data: {json.dumps({'type': 'progress', 'phase': task.get('current_phase', 'unknown'), 'progress': task.get('progress', 0)})}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """获取任务状态"""
    task = db.get_audit_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs = db.get_conversation_logs(task_id)

    return {
        "task": task,
        "logs": logs,
        "status": "success"
    }


@router.get("/tasks")
async def list_tasks(user: Dict[str, Any] = Depends(require_auth), limit: int = 20):
    """列出用户任务"""
    tasks = db.list_audit_tasks(limit=limit)
    return {
        "tasks": tasks,
        "total": len(tasks),
        "status": "success"
    }
