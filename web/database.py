#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库模块 - 使用 SQLite 存储审计数据
"""

import sqlite3
import json
import os
import asyncio
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from web.models import (
    ScanUrlInfo, AuditResult, ExploitResult, TraceResult, ScanResult, CodeContext
)

# 数据库文件路径
DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "audit.db"


def get_db_path() -> str:
    """获取数据库路径"""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return str(DB_PATH)


@contextmanager
def get_connection():
    """获取数据库连接（同步）"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


async def get_connection_async():
    """获取数据库连接（异步）"""
    import aiosqlite
    return await aiosqlite.connect(get_db_path(), check_same_thread=False)


def init_db():
    """初始化数据库表结构"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME
        )
    """)

    # 项目表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            project_path TEXT UNIQUE NOT NULL,
            project_type TEXT DEFAULT 'c',
            uploaded_file TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 审计任务表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            project_path TEXT NOT NULL,
            scan_path TEXT DEFAULT 'scan.py',
            max_turns INTEGER DEFAULT 50,
            status TEXT DEFAULT 'pending',
            total_functions INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (project_path) REFERENCES projects(project_path)
        )
    """)

    # URL 扫描结果表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            url_path TEXT NOT NULL,
            callback_func TEXT NOT NULL,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            code_snippet TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES audit_tasks(task_id)
        )
    """)

    # 审计结果表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id INTEGER NOT NULL,
            vulnerability_type TEXT NOT NULL,
            is_vulnerable INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            description TEXT NOT NULL,
            taint_flow TEXT,
            recommendation TEXT,
            code_map TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trace_id) REFERENCES trace_results(id)
        )
    """)

    # PoC 结果表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exploit_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id INTEGER NOT NULL,
            vulnerability_type TEXT NOT NULL,
            success INTEGER NOT NULL,
            poc_command TEXT NOT NULL,
            output TEXT,
            error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trace_id) REFERENCES trace_results(id)
        )
    """)

    # Trace 结果表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trace_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            func_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            code_snippet TEXT,
            total_vulnerabilities INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES audit_tasks(task_id)
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_tasks_status ON audit_tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_tasks_project ON audit_tasks(project_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_task ON scan_results(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trace_results_task ON trace_results(task_id)")

    conn.commit()
    conn.close()


# ========== 项目操作 ==========

def save_project(user_id: int, project_name: str, project_path: str, project_type: str = "c", uploaded_file: str = None) -> int:
    """保存项目信息"""
    # 确保表结构是最新的
    add_project_user_column()

    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    # 检查表中是否存在 user_id 列
    cursor.execute("PRAGMA table_info(projects)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'user_id' in columns:
        cursor.execute("""
            INSERT OR REPLACE INTO projects (user_id, project_name, project_path, project_type, uploaded_file, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, project_name, project_path, project_type, uploaded_file))
    else:
        cursor.execute("""
            INSERT OR REPLACE INTO projects (project_path, project_type, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (project_path, project_type))

    conn.commit()
    conn.close()
    return cursor.lastrowid


def get_project(project_path: str) -> Optional[Dict[str, Any]]:
    """获取项目信息"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE project_path = ?", (project_path,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def add_project_user_column():
    """为项目表添加 user_id 列（用于升级旧数据库）"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(projects)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'user_id' not in columns:
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
        except Exception:
            pass  # 列已存在或添加失败

    conn.close()


def get_project_by_id(project_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取项目信息"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_projects(user_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
    """列出项目"""
    # 确保表结构是最新的
    add_project_user_column()

    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查表中是否存在 user_id 列
        cursor.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'user_id' in columns and user_id:
            cursor.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?", (user_id, limit))
        else:
            cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def delete_project(project_id: int, user_id: int = None) -> bool:
    """删除项目"""
    # 确保表结构是最新的
    add_project_user_column()

    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    # 检查表中是否存在 user_id 列
    cursor.execute("PRAGMA table_info(projects)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'user_id' in columns and user_id:
        cursor.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    else:
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ========== 审计任务操作 ==========

def create_audit_task(task_id: str, project_path: str, scan_path: str = "scan.py", max_turns: int = 50) -> int:
    """创建审计任务"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO audit_tasks (task_id, project_path, scan_path, max_turns, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (task_id, project_path, scan_path, max_turns))

    conn.commit()
    conn.close()
    return cursor.lastrowid


def update_audit_task_status(task_id: str, status: str, total: int = 0, completed_at: str = None):
    """更新任务状态"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    if completed_at:
        cursor.execute("""
            UPDATE audit_tasks
            SET status = ?, total_functions = ?, completed_at = ?
            WHERE task_id = ?
        """, (status, total, completed_at, task_id))
    else:
        cursor.execute("""
            UPDATE audit_tasks
            SET status = ?, total_functions = ?
            WHERE task_id = ?
        """, (status, total, task_id))

    conn.commit()
    conn.close()


def get_audit_task(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务信息"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def list_audit_tasks(project_path: str = None, limit: int = 10) -> List[Dict[str, Any]]:
    """列出任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if project_path:
            cursor.execute(
                "SELECT * FROM audit_tasks WHERE project_path = ? ORDER BY created_at DESC LIMIT ?",
                (project_path, limit)
            )
        else:
            cursor.execute("SELECT * FROM audit_tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


# ========== 扫描结果操作 ==========

def save_scan_results(task_id: str, urls: List[ScanUrlInfo]):
    """保存扫描结果"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    for url in urls:
        cursor.execute("""
            INSERT INTO scan_results (task_id, url_path, callback_func, file_path, start_line, end_line, code_snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            url.url_path,
            url.callback_func,
            url.file_path,
            url.start_line,
            url.end_line,
            url.code_snippet
        ))

    conn.commit()
    conn.close()


def get_scan_results(task_id: str) -> List[Dict[str, Any]]:
    """获取扫描结果"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scan_results WHERE task_id = ?", (task_id,))
        return [dict(row) for row in cursor.fetchall()]


# ========== Trace 结果操作 ==========

def save_trace_result(task_id: str, result: TraceResult) -> int:
    """保存 Trace 结果"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trace_results (task_id, func_name, file_path, start_line, end_line, code_snippet, total_vulnerabilities, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        result.func_name,
        result.file_path,
        result.start_line,
        result.end_line,
        json.dumps(result.code_snippet) if result.code_snippet else None,
        len(result.audit_results),
        'completed'
    ))

    trace_id = cursor.lastrowid

    # 保存审计结果
    for audit_result in result.audit_results:
        cursor.execute("""
            INSERT INTO audit_results (trace_id, vulnerability_type, is_vulnerable, confidence, description, taint_flow, recommendation, code_map)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id,
            audit_result.vulnerability_type,
            1 if audit_result.is_vulnerable else 0,
            audit_result.confidence,
            audit_result.description,
            audit_result.taint_flow,
            audit_result.recommendation,
            json.dumps([dict(c) for c in audit_result.code_map]) if audit_result.code_map else None
        ))

    # 保存 PoC 结果
    for exploit_result in result.exploit_results:
        cursor.execute("""
            INSERT INTO exploit_results (trace_id, vulnerability_type, success, poc_command, output, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            trace_id,
            exploit_result.vulnerability_type,
            1 if exploit_result.success else 0,
            exploit_result.poc_command,
            exploit_result.output,
            exploit_result.error
        ))

    conn.commit()
    conn.close()
    return trace_id


def get_trace_results(task_id: str) -> List[Dict[str, Any]]:
    """获取 Trace 结果"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trace_results WHERE task_id = ?", (task_id,))
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            # 获取审计结果
            cursor.execute("SELECT * FROM audit_results WHERE trace_id = ?", (result['id'],))
            result['audit_results'] = [dict(r) for r in cursor.fetchall()]
            # 获取 PoC 结果
            cursor.execute("SELECT * FROM exploit_results WHERE trace_id = ?", (result['id'],))
            result['exploit_results'] = [dict(r) for r in cursor.fetchall()]
            results.append(result)
        return results


def get_trace_result_by_id(trace_id: int) -> Optional[Dict[str, Any]]:
    """获取单个 Trace 结果"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trace_results WHERE id = ?", (trace_id,))
        row = cursor.fetchone()
        if not row:
            return None

        result = dict(row)
        # 获取审计结果
        cursor.execute("SELECT * FROM audit_results WHERE trace_id = ?", (trace_id,))
        result['audit_results'] = [dict(r) for r in cursor.fetchall()]
        # 获取 PoC 结果
        cursor.execute("SELECT * FROM exploit_results WHERE trace_id = ?", (trace_id,))
        result['exploit_results'] = [dict(r) for r in cursor.fetchall()]
        return result


# ========== 统计信息 ==========

def get_stats() -> Dict[str, Any]:
    """获取统计信息"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 折叠调用以获取统计信息
        cursor.execute("SELECT COUNT(DISTINCT project_path) FROM projects")
        projects_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM audit_tasks WHERE status = 'completed'")
        completed_tasks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM audit_results WHERE is_vulnerable = 1")
        vulnerable_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM audit_results ar
            JOIN trace_results tr ON ar.trace_id = tr.id
            WHERE ar.is_vulnerable = 1 AND ar.confidence = 'high'
        """)
        high_risk_count = cursor.fetchone()[0]

        return {
            "total_projects": projects_count,
            "completed_audits": completed_tasks,
            "total_vulnerabilities": vulnerable_count,
            "high_risk_vulnerabilities": high_risk_count
        }


# ========== 用户操作 ==========

import hashlib
import secrets


def hash_password(password: str) -> str:
    """哈希密码"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    try:
        salt, hash_value = password_hash.split('$')
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return pwd_hash.hex() == hash_value
    except Exception:
        return False


def init_default_admin():
    """初始化默认管理员账户"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    # 检查是否已存在 admin 用户
    cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if cursor.fetchone() is None:
        password_hash = hash_password("admin")
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, role, is_active)
            VALUES (?, ?, ?, 'admin', 1)
        """, ("admin", password_hash, "admin@localhost"))
        conn.commit()
        print("默认管理员账户已创建: admin/admin")

    conn.close()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """根据用户名获取用户"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取用户"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def create_user(username: str, password: str, email: Optional[str] = None, role: str = "user") -> Optional[int]:
    """创建新用户"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    try:
        password_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (username, password_hash, email, role))
        conn.commit()
        conn.close()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return None


def update_user(user_id: int, **kwargs) -> bool:
    """更新用户信息"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()

    fields = []
    values = []
    for key, value in kwargs.items():
        if key in ['email', 'role', 'is_active', 'password']:
            if key == 'password':
                fields.append("password_hash = ?")
                values.append(hash_password(value))
            else:
                fields.append(f"{key} = ?")
                values.append(value)

    if not fields:
        conn.close()
        return False

    values.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """删除用户"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def list_users(role: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """列出用户"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if role:
            cursor.execute("SELECT id, username, email, role, is_active, created_at, last_login FROM users WHERE role = ? ORDER BY created_at DESC LIMIT ?", (role, limit))
        else:
            cursor.execute("SELECT id, username, email, role, is_active, created_at, last_login FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]


def update_last_login(username: str):
    """更新最后登录时间"""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """用户认证"""
    user = get_user_by_username(username)
    if user and verify_password(password, user['password_hash']):
        update_last_login(username)
        return user
    return None


def is_admin(user_id: int) -> bool:
    """检查用户是否为管理员"""
    user = get_user_by_id(user_id)
    return user and user.get('role') == 'admin'
