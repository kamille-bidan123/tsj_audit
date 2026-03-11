#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shell 命令执行工具

支持多 session 管理，每个 session 维护独立的工作目录。
支持本地模式和 Docker 模式。
配置从 cli 全局配置读取。
"""

import subprocess
import uuid
import os
import time
import pty
import fcntl
import atexit
import signal
import re
from typing import Dict
from tools.registry import ToolRegistry


def _get_global_config() -> dict:
    """从 cli 全局配置读取"""
    try:
        from cli import get_global_config
        return get_global_config()
    except ImportError:
        return {}


class SessionInfo:
    """Shell session 信息"""

    def __init__(
        self,
        session_id: str,
        process: subprocess.Popen = None,
        master_fd: int = None,
        container_id: str = None,
        docker_process: subprocess.Popen = None,
        docker_master_fd: int = None,
    ):
        self.session_id = session_id
        self.process = process  # 本地模式的 bash 进程
        self.master_fd = master_fd  # 本地模式的 pty fd
        self.container_id = container_id  # Docker 模式的容器 ID
        self.docker_process = docker_process  # Docker 模式的 docker exec 进程
        self.docker_master_fd = docker_master_fd  # Docker 模式的 pty fd
        self.cwd: str = "."  # 当前工作目录
        self.created_at: float = time.time()
        self.is_docker: bool = container_id is not None

    def get_cwd(self) -> str:
        """获取 session 当前工作目录"""
        return self.cwd


@ToolRegistry.register
class ShellTool:
    """Shell 命令执行，支持多 session（本地模式和 Docker 模式）"""

    name = "shell_tool"
    description = "执行系统命令和脚本，支持多 session 管理"

    # Session 管理（类变量，所有实例共享）
    _sessions: Dict[str, SessionInfo] = {}
    _cleanup_registered: bool = False

    commands = {
        "run_command": {
            "description": "执行系统 shell 命令（临时 session，执行完关闭）",
            "usage": "run_command <command>",
            "examples": [
                "run_command ls -la",
                "run_command git status",
                "run_command python test.py",
            ],
        },
        "create_session": {
            "description": "创建新的 shell session",
            "usage": "create_session [name]",
            "examples": [
                "create_session",
                "create_session build_session",
            ],
        },
        "session_exec": {
            "description": "在指定 session 中执行命令",
            "usage": "session_exec <session_id> <command>",
            "examples": [
                "session_exec abc123 cd /app/src",
                "session_exec abc123 python build.py",
            ],
        },
        "close_session": {
            "description": "关闭指定的 session",
            "usage": "close_session <session_id>",
            "examples": [
                "close_session abc123",
            ],
        },
        "list_sessions": {
            "description": "列出所有活跃的 session",
            "usage": "list_sessions",
            "examples": [
                "list_sessions",
            ],
        },
    }

    def _get_config(self) -> dict:
        """每次执行时获取最新配置"""
        return _get_global_config()

    def execute(self, command: str, args: str) -> str:
        if command == "run_command":
            return self._run_command(args)
        elif command == "create_session":
            return self._create_session(args)
        elif command == "session_exec":
            return self._session_exec(args)
        elif command == "close_session":
            return self._close_session(args)
        elif command == "list_sessions":
            return self._list_sessions()
        else:
            return f"错误：未知命令 '{command}'"

    def _run_command(self, args: str) -> str:
        """执行临时命令（一次性 session）"""
        config = self._get_config()
        container_id = config.get("docker_container") or config.get("container_id")
        project_path = config.get("project_path", ".")

        if container_id:
            # Docker 模式
            cmd = f"docker exec {container_id} bash -c '{args}'"
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr
                return output.strip() or "(无输出)"
            except subprocess.TimeoutExpired:
                return "错误：命令执行超时"
            except Exception as e:
                return f"错误：{e}"
        else:
            # 本地模式
            try:
                result = subprocess.run(
                    args,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=project_path,
                )
                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr
                return output.strip() or "(无输出)"
            except subprocess.TimeoutExpired:
                return "错误：命令执行超时"
            except Exception as e:
                return f"错误：{e}"

    def _create_session(self, args: str) -> str:
        """创建新的 shell session"""
        self._register_cleanup()
        config = self._get_config()
        container_id = config.get("docker_container") or config.get("container_id")
        workdir = config.get("docker_workdir", "/app")
        project_path = config.get("project_path", ".")

        session_id = args.strip() if args.strip() else str(uuid.uuid4())[:8]

        # 检查是否已存在
        if session_id in self._sessions:
            return f"错误：session '{session_id}' 已存在"

        if container_id:
            # Docker 模式：使用 docker exec -it 创建交互式 bash
            try:
                master_fd, slave_fd = pty.openpty()

                process = subprocess.Popen(
                    ["docker", "exec", "-it", container_id, "bash", "--norc", "--noprofile", "-i"],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                )

                os.close(slave_fd)

                # 设置为非阻塞模式
                flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                self._sessions[session_id] = SessionInfo(
                    session_id=session_id,
                    docker_process=process,
                    docker_master_fd=master_fd,
                    container_id=container_id,
                )
                self._sessions[session_id].cwd = workdir
                self._sessions[session_id].is_docker = True

                # 清空初始输出（bash banner 等）
                time.sleep(0.3)
                try:
                    os.read(master_fd, 4096)
                except BlockingIOError:
                    pass

                return f"已创建 session: {session_id} (Docker: {container_id}, cwd: {workdir})"
            except Exception as e:
                return f"错误：创建 session 失败 - {e}"
        else:
            # 本地模式：使用 pty 创建交互式 bash
            try:
                master_fd, slave_fd = pty.openpty()

                process = subprocess.Popen(
                    ["bash", "--norc", "--noprofile", "-i"],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                    cwd=project_path,
                )

                os.close(slave_fd)

                flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                self._sessions[session_id] = SessionInfo(
                    session_id=session_id,
                    process=process,
                    master_fd=master_fd,
                )
                self._sessions[session_id].cwd = project_path
                self._sessions[session_id].is_docker = False

                # 清空初始输出
                time.sleep(0.2)
                try:
                    os.read(master_fd, 4096)
                except BlockingIOError:
                    pass

                return f"已创建 session: {session_id} (当前目录：{project_path})"
            except Exception as e:
                return f"错误：创建 session 失败 - {e}"

    def _session_exec(self, args: str) -> str:
        """在指定 session 中执行命令"""
        parts = args.split(" ", 1)
        if len(parts) != 2:
            return "错误：用法 session_exec <session_id> <command>"

        session_id, command = parts

        if session_id not in self._sessions:
            return f"错误：session '{session_id}' 不存在"

        session = self._sessions[session_id]

        # 检查 session 是否可用
        if session.is_docker:
            if session.docker_process and session.docker_process.poll() is not None:
                return f"错误：session '{session_id}' 已终止"
        else:
            if session.process and session.process.poll() is not None:
                return f"错误：session '{session_id}' 已终止"

        return self._pty_session_exec(session, command)

    def _pty_session_exec(self, session: SessionInfo, command: str) -> str:
        """通过 pty 在 session 中执行命令（本地和 Docker 通用）"""
        master_fd = session.master_fd or session.docker_master_fd
        if master_fd is None:
            return f"错误：session '{session.session_id}' 没有有效的 pty"

        try:
            # 发送命令
            os.write(master_fd, (command + "\n").encode())

            # 等待命令执行
            sleep_time = 0.5 if "|" in command or ">>" in command else 0.3
            time.sleep(sleep_time)

            # 发送 pwd 命令获取当前目录
            os.write(master_fd, b'echo ""\necho "__SESSION_CWD__:$PWD"\n')
            time.sleep(0.2)

            # 读取输出
            output_lines = []
            cwd_line = ""
            timeout = time.time() + 10
            found_marker = False

            while time.time() < timeout:
                try:
                    data = os.read(master_fd, 4096).decode()
                    if not data:
                        break

                    lines = data.split("\n")
                    for line in lines:
                        line = self._clean_ansi(line)

                        if "__SESSION_CWD__:" in line:
                            cwd_line = line
                            found_marker = True
                        else:
                            output_lines.append(line)

                        if found_marker and time.time() > timeout - 2:
                            break

                except BlockingIOError:
                    time.sleep(0.05)
                except OSError:
                    break

            # 清理输出
            cleaned_lines = []
            for line in output_lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("bash"):
                    continue
                if line == "__SESSION_CWD__":
                    continue
                if command and line == command:
                    continue
                cleaned_lines.append(line)

            output = "\n".join(cleaned_lines).strip()

            # 更新 cwd
            if cwd_line and "__SESSION_CWD__:" in cwd_line:
                session.cwd = cwd_line.split("__SESSION_CWD__:")[1]

            return output or "(无输出)"
        except Exception as e:
            return f"错误：执行失败 - {e}"

    def _clean_ansi(self, text: str) -> str:
        """清理 ANSI 转义序列和控制字符"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)
        text = re.sub(r'[\x00-\x1F\x7F]', '', text)
        return text

    def _close_session(self, args: str) -> str:
        """关闭指定 session"""
        session_id = args.strip()

        if not session_id:
            return "错误：用法 close_session <session_id>"

        if session_id not in self._sessions:
            return f"错误：session '{session_id}' 不存在"

        session = self._sessions[session_id]

        try:
            master_fd = session.master_fd or session.docker_master_fd

            if master_fd is not None:
                try:
                    os.write(master_fd, b"exit\n")
                    time.sleep(0.1)
                except OSError:
                    pass

            # 终止进程
            process = session.docker_process if session.is_docker else session.process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

            # 关闭 master_fd
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass

            del self._sessions[session_id]
            return f"已关闭 session: {session_id}"
        except Exception as e:
            return f"错误：关闭失败 - {e}"

    def _list_sessions(self) -> str:
        """列出所有活跃的 session"""
        if not self._sessions:
            return "(没有活跃的 session)"

        lines = []
        for session_id, session in self._sessions.items():
            if session.is_docker:
                if session.docker_process and session.docker_process.poll() is not None:
                    lines.append(f"  {session_id} [已结束] Docker: {session.container_id} cwd: {session.cwd}")
                else:
                    lines.append(f"  {session_id} [活跃] Docker: {session.container_id} cwd: {session.cwd}")
            else:
                if session.process and session.process.poll() is not None:
                    lines.append(f"  {session_id} [已结束] cwd: {session.cwd}")
                else:
                    lines.append(f"  {session_id} [活跃] cwd: {session.cwd}")

        return "活跃 session 列表:\n" + "\n".join(lines)

    @classmethod
    def _register_cleanup(cls):
        """注册退出清理函数"""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_all_sessions)
            signal.signal(signal.SIGTERM, cls._signal_handler)
            signal.signal(signal.SIGINT, cls._signal_handler)
            cls._cleanup_registered = True

    @classmethod
    def _signal_handler(cls, signum, frame):
        """信号处理"""
        cls._cleanup_all_sessions()
        exit(1)

    @classmethod
    def _cleanup_all_sessions(cls):
        """清理所有 session（程序退出时调用）"""
        session_ids = list(cls._sessions.keys())
        for session_id in session_ids:
            try:
                session = cls._sessions[session_id]
                master_fd = session.master_fd or session.docker_master_fd

                if master_fd is not None:
                    try:
                        os.write(master_fd, b"exit\n")
                    except OSError:
                        pass

                process = session.docker_process if session.is_docker else session.process
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()

                if master_fd is not None:
                    try:
                        os.close(master_fd)
                    except OSError:
                        pass

            except Exception:
                pass

        cls._sessions.clear()
