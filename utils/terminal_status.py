#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Textual-powered terminal UI for long-running audits."""

from __future__ import annotations

import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from rich.markup import escape
from rich.text import Text

from utils.web_status import RuntimeStatusServer


try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import DataTable, Footer, RichLog, Static
    _TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover - graceful fallback when textual is not installed.
    _TEXTUAL_AVAILABLE = False

    class _MissingApp:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return None

    class _MissingWidget:
        def __init__(self, *args, **kwargs):
            pass

    class _MissingContainer:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def Binding(*args, **kwargs):  # type: ignore[no-redef]
        return None

    App = _MissingApp  # type: ignore[assignment,misc]
    ComposeResult = Any  # type: ignore[assignment]
    Vertical = _MissingContainer  # type: ignore[assignment]
    DataTable = Footer = RichLog = Static = _MissingWidget  # type: ignore[assignment]


@dataclass
class FunctionState:
    name: str
    file_path: str = ""
    stage: str = ""
    audit_type: str = ""
    status: str = "pending"


class AuditRichLog(RichLog):
    """RichLog that lets the app pause auto-follow on user scroll."""

    def _pause_auto_scroll_for_user_scroll(self) -> None:
        pause = getattr(self.app, "pause_log_auto_scroll", None)
        if callable(pause):
            pause()

    def action_scroll_up(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_scroll_up()

    def action_scroll_down(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_scroll_down()

    def action_scroll_home(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_scroll_home()

    def action_scroll_end(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_scroll_end()

    def action_page_up(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_page_up()

    def action_page_down(self) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super().action_page_down()

    def _on_mouse_scroll_up(self, event) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super()._on_mouse_scroll_up(event)

    def _on_mouse_scroll_down(self, event) -> None:
        self._pause_auto_scroll_for_user_scroll()
        super()._on_mouse_scroll_down(event)


class _TuiStream:
    def __init__(self, owner: "TerminalStatus", original, *, style: str | None = None):
        self.owner = owner
        self.original = original
        self.style = style
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._write_line(line)
        return len(text)

    def flush(self) -> None:
        self.original.flush()
        if self._buffer:
            self._write_line(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return self.original.isatty()

    def _write_line(self, line: str) -> None:
        if self.style:
            self.owner.log(f"[{self.style}]{escape(line)}[/{self.style}]")
        else:
            self.owner.log(line)


class _TeeStream:
    """Mirror command-line output into the live web status log."""

    def __init__(self, owner: "TerminalStatus", original, *, stream: str):
        self.owner = owner
        self.original = original
        self.stream = stream
        self._buffer = ""

    def write(self, text: str) -> int:
        written = self.original.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self.owner.log(line, stream=self.stream)
        return written if isinstance(written, int) else len(text)

    def flush(self) -> None:
        self.original.flush()
        if self._buffer:
            self.owner.log(self._buffer, stream=self.stream)
            self._buffer = ""

    def isatty(self) -> bool:
        return self.original.isatty()

    def fileno(self) -> int:
        return self.original.fileno()

    def __getattr__(self, name: str):
        return getattr(self.original, name)


class AuditStatusApp(App):
    """Textual dashboard for audit progress."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #log {
        height: 1fr;
        border: solid $primary;
    }

    #functions {
        height: 40%;
        display: none;
        border: solid $accent;
    }

    #status {
        height: 3;
        dock: bottom;
        content-align: left middle;
        background: $boost;
        color: $text;
        padding: 0 1;
    }

    #permission {
        display: none;
        height: auto;
        border: heavy yellow;
        background: darkred;
        color: white;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("g", "toggle_functions", "展开/收起函数"),
        Binding("l", "follow_log", "日志自动跟随"),
        Binding("ctrl+c", "copy_selection", "复制选中"),
        Binding("escape", "clear_selection", "清除选中", show=False),
        Binding("o", "permission_once", "批准本次", show=False),
        Binding("a", "permission_always", "永久批准", show=False),
        Binding("r", "permission_reject", "拒绝", show=False),
        Binding("y", "confirm_yes", "确认", show=False),
        Binding("n", "confirm_no", "取消", show=False),
        Binding("q", "noop", "运行中不可退出", show=False),
    ]

    def __init__(self, owner: "TerminalStatus", target: Callable[[], None]):
        super().__init__()
        self.owner = owner
        self.target = target
        self.functions_visible = False
        self.log_auto_scroll = True
        self.target_finished = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield AuditRichLog(id="log", wrap=True, markup=True)
            yield Static("", id="permission")
            yield DataTable(id="functions")
            yield Static("", id="status")
            yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#functions", DataTable)
        table.add_columns("状态", "函数", "阶段", "漏洞类型", "文件")
        table.cursor_type = "row"
        self.owner._app_ready.set()
        self._refresh_all()
        thread = threading.Thread(target=self._run_target, daemon=True)
        thread.start()

    def _run_target(self) -> None:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = _TuiStream(self.owner, old_stdout)
        sys.stderr = _TuiStream(self.owner, old_stderr, style="red")
        had_error = False
        try:
            self.target()
        except BaseException as exc:
            had_error = True
            log_path = self.owner._capture_target_error(exc)
            detail = f"；完整 traceback: {log_path}" if log_path else ""
            self.owner.log(f"[bold red]运行失败:[/bold red] {exc!r}{detail}")
            traceback_text = getattr(self.owner, "_target_traceback", "")
            if not isinstance(traceback_text, str) or not traceback_text:
                traceback_text = traceback.format_exc()
            for line in traceback_text.rstrip().splitlines():
                self.owner.log(f"[red]{escape(line)}[/red]")
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.target_finished = True
            self.owner.mark_tui_finished(error=had_error)

    def action_toggle_functions(self) -> None:
        self.functions_visible = not self.functions_visible
        table = self.query_one("#functions", DataTable)
        table.display = self.functions_visible
        if self.functions_visible:
            table.focus()
        else:
            self.query_one("#log", RichLog).focus()

    def pause_log_auto_scroll(self) -> None:
        self.log_auto_scroll = False
        log = self.query_one("#log", RichLog)
        log.auto_scroll = False
        self._refresh_status()

    def action_follow_log(self) -> None:
        self.log_auto_scroll = True
        log = self.query_one("#log", RichLog)
        log.auto_scroll = True
        log.scroll_end(animate=False)
        log.focus()
        self._refresh_status()

    def action_copy_selection(self) -> None:
        selected = self.screen.get_selected_text()
        if not selected:
            self.notify("没有选中文本。拖选日志或状态后按 Ctrl+C 复制。", severity="warning")
            return
        self.copy_to_clipboard(selected)
        self.notify("已复制选中文本", severity="information")

    def action_clear_selection(self) -> None:
        self.screen.clear_selection()

    def action_permission_once(self) -> None:
        self.owner._reply_permission_from_tui("once")

    def action_permission_always(self) -> None:
        self.owner._reply_permission_from_tui("always")

    def action_permission_reject(self) -> None:
        self.owner._reply_permission_from_tui("reject")

    def action_confirm_yes(self) -> None:
        self.owner._reply_confirmation_from_tui(True)

    def action_confirm_no(self) -> None:
        self.owner._reply_confirmation_from_tui(False)

    def action_noop(self) -> None:
        if self.target_finished:
            self.exit()
            return
        self.notify("审计正在运行，完成或异常后可按 q 退出。", severity="warning")

    def refresh_from_owner(self) -> None:
        self._refresh_all()

    def write_log(self, line: str) -> None:
        log = self.query_one("#log", RichLog)
        log.auto_scroll = self.log_auto_scroll
        log.write(line)

    def _refresh_all(self) -> None:
        self._refresh_status()
        self._refresh_functions()
        self._refresh_permission()

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        status.update(
            "[bold cyan]阶段[/bold cyan] "
            f"[bold white]{self.owner.stage or '-'}[/bold white]   "
            "[bold cyan]函数[/bold cyan] "
            f"[bold yellow]{self.owner.function_name or '-'}[/bold yellow]   "
            "[bold cyan]类型[/bold cyan] "
            f"[bold magenta]{self.owner.audit_type or '-'}[/bold magenta]   "
            "[bold cyan]runtime[/bold cyan] "
            f"[green]{self.owner.runtime or '-'}[/green]   "
            "[bold cyan]session[/bold cyan] "
            f"[dim]{self.owner.session_id or '-'}[/dim]   "
            f"[dim]日志跟随 {'on' if self.log_auto_scroll else 'off'}；"
            f"{self.owner.tui_exit_hint}；"
            "g 展开/收起，l 恢复日志跟随，拖选后 Ctrl+C 复制[/dim]"
        )

    def _refresh_functions(self) -> None:
        table = self.query_one("#functions", DataTable)
        table.clear()
        for item in self.owner.functions:
            table.add_row(*self._function_row(item))

    def _function_row(self, item: FunctionState) -> tuple[Text, Text, Text, Text, Text]:
        if item.status == "running":
            style = "bold yellow"
            status = "running"
        elif item.status == "done":
            style = "white"
            status = "done"
        else:
            style = "dim"
            status = "pending"
        return (
            Text(status, style=style),
            Text(item.name, style=style),
            Text(item.stage or "-", style=style),
            Text(item.audit_type or "-", style=style),
            Text(item.file_path, style=style),
        )

    def _refresh_permission(self) -> None:
        panel = self.query_one("#permission", Static)
        request = self.owner.permission_request
        confirmation = self.owner.confirmation_prompt
        if confirmation is not None:
            panel.display = True
            panel.update(
                "[bold yellow]需要确认[/bold yellow]\n"
                f"{confirmation}\n"
                "[bold]按 y=继续, n=终止[/bold]"
            )
            return
        if request is None:
            panel.display = False
            panel.update("")
            return
        panel.display = True
        patterns = request.get("patterns") or []
        tool = request.get("tool") or {}
        metadata = request.get("metadata") or {}
        text = (
            "[bold yellow]OPENCODE 权限请求[/bold yellow]\n"
            f"Session: {self.owner.permission_session_id}\n"
            f"Permission ID: {request.get('id')}\n"
            f"申请权限: [bold red]{request.get('permission')}[/bold red]\n"
            f"影响范围: {', '.join(map(str, patterns)) or '-'}\n"
            f"Tool: messageID={tool.get('messageID')} callID={tool.get('callID')}\n"
            f"动作详情: {metadata or '-'}\n"
            "[bold]按 o=批准本次, a=永久批准, r=拒绝[/bold]"
        )
        panel.update(text)


class TerminalStatus:
    """Process-wide facade used by the audit pipeline."""

    def __init__(self) -> None:
        self.enabled = False
        self.app: Optional[AuditStatusApp] = None
        self.web_server: RuntimeStatusServer | None = None
        self.web_url = ""
        self.lock = threading.RLock()
        self._app_ready = threading.Event()
        self._target_error: BaseException | None = None
        self._target_traceback = ""
        self._target_error_log_path: Path | None = None
        self.stage = "启动"
        self.function_name = "-"
        self.audit_type = "-"
        self.runtime = "-"
        self.session_id = "-"
        self.tui_exit_hint = "运行中按 q 不退出"
        self.functions: list[FunctionState] = []
        self.permission_request: dict[str, Any] | None = None
        self.permission_session_id = "-"
        self._permission_event = threading.Event()
        self._permission_reply = "reject"
        self.confirmation_prompt: str | None = None
        self._confirmation_event = threading.Event()
        self._confirmation_reply = False
        self.logs: list[dict[str, Any]] = []
        self._log_seq = 0

    def can_run_tui(self) -> bool:
        return False

    def run_with(self, target: Callable[[], None]) -> None:
        self._target_error = None
        self._target_traceback = ""
        self._target_error_log_path = None
        self.tui_exit_hint = "运行中；Web UI 随进程退出"
        self._ensure_web_ui()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = _TeeStream(self, old_stdout, stream="stdout")
        sys.stderr = _TeeStream(self, old_stderr, stream="stderr")
        had_error = False
        try:
            target()
        except BaseException as exc:
            had_error = True
            log_path = self._capture_target_error(exc)
            detail = f"；完整 traceback: {log_path}" if log_path else ""
            self.log(f"运行失败: {exc!r}{detail}", stream="stderr")
            traceback_text = self._target_traceback or traceback.format_exc()
            for line in traceback_text.rstrip().splitlines():
                self.log(line, stream="stderr")
            raise
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.mark_tui_finished(error=had_error)

    def start(self) -> None:
        if self.app:
            self._refresh()

    def stop(self) -> None:
        if self.app:
            try:
                self.app.call_from_thread(self.app.exit)
            except Exception:
                pass
        if self.web_server:
            try:
                self.web_server.stop()
            except Exception:
                pass
            self.web_server = None

    def mark_tui_finished(self, *, error: bool) -> None:
        with self.lock:
            if error:
                self.stage = "异常退出"
                self.tui_exit_hint = "异常退出；查看命令行或最终 HTML 报告"
            else:
                self.tui_exit_hint = "流程结束；查看命令行或最终 HTML 报告"
            self._refresh()

    def _capture_target_error(self, exc: BaseException) -> Path | None:
        self._target_error = exc
        self._target_traceback = traceback.format_exc()
        self._target_error_log_path = self._write_target_error_log(self._target_traceback)
        return self._target_error_log_path

    def _write_target_error_log(self, traceback_text: str) -> Path | None:
        try:
            from config import get_config

            output_dir = Path(get_config().output_dir or ".")
        except Exception:
            output_dir = Path(".")

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            log_path = output_dir / "tui_error.log"
            timestamp = datetime.now().isoformat(timespec="seconds")
            log_path.write_text(
                f"[{timestamp}] TUI target failed\n{traceback_text}",
                encoding="utf-8",
            )
            return log_path
        except OSError:
            return None

    def pause_input(self) -> None:
        # Textual owns input; permission prompts are handled by key bindings.
        return

    def resume_input(self) -> None:
        return

    def log(self, line: str, *, stream: str = "status") -> None:
        with self.lock:
            self._log_seq += 1
            self.logs.append(
                {
                    "seq": self._log_seq,
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "stream": stream,
                    "line": str(line),
                }
            )
            if len(self.logs) > 2000:
                self.logs = self.logs[-2000:]
        if self.app and self._app_ready.is_set():
            try:
                self.app.call_from_thread(self.app.write_log, line)
            except Exception:
                pass

    def set_stage(self, stage: str, *, function_name: str | None = None, audit_type: str | None = None) -> None:
        with self.lock:
            self.stage = stage
            if function_name is not None:
                self.function_name = function_name
            if audit_type is not None:
                self.audit_type = audit_type or "-"
            self._refresh()

    def set_runtime(self, runtime: str, session_id: str | None = None) -> None:
        with self.lock:
            self.runtime = runtime
            if session_id:
                self.session_id = session_id
            self._refresh()

    def set_functions(self, functions: list[Any]) -> None:
        with self.lock:
            existing = {state.name: state for state in self.functions}
            ordered: list[FunctionState] = []
            for func in functions:
                name = getattr(func, "func_name", None) or str(func)
                file_path = getattr(func, "file_path", "")
                state = existing.get(name) or FunctionState(name=name)
                state.file_path = file_path or state.file_path
                ordered.append(state)
            self.functions = ordered
            self._refresh()

    def start_function(self, name: str, file_path: str = "") -> None:
        with self.lock:
            self.function_name = name
            self.audit_type = "-"
            state = self._state_for(name)
            state.file_path = file_path or state.file_path
            state.stage = "Trace"
            state.status = "running"
            self._refresh()

    def complete_function(self, name: str) -> None:
        with self.lock:
            state = self._state_for(name)
            state.status = "done"
            state.stage = "完成"
            self._refresh()

    def restore_function(self, name: str, file_path: str = "") -> None:
        with self.lock:
            state = self._state_for(name)
            state.file_path = file_path or state.file_path
            state.stage = "已恢复"
            state.status = "done"
            self._refresh()

    def set_function_audit(self, name: str, audit_type: str) -> None:
        with self.lock:
            self.function_name = name
            self.audit_type = audit_type
            state = self._state_for(name)
            state.stage = "Audit"
            state.audit_type = audit_type
            state.status = "running"
            self._refresh()

    def ask_permission(self, request: dict[str, Any], *, session_id: str) -> str | None:
        if not self.app and not self.web_server:
            return None
        with self.lock:
            self.permission_request = request
            self.permission_session_id = session_id
            self._permission_reply = "reject"
            self._permission_event.clear()
            self._refresh()
        self._permission_event.wait()
        with self.lock:
            reply = self._permission_reply
            self.permission_request = None
            self.permission_session_id = "-"
            self._refresh()
        return reply

    def ask_confirmation(self, prompt: str) -> bool | None:
        if not self.app and not self.web_server:
            return None
        with self.lock:
            self.confirmation_prompt = prompt
            self._confirmation_reply = False
            self._confirmation_event.clear()
            self._refresh()
        self._confirmation_event.wait()
        with self.lock:
            reply = self._confirmation_reply
            self.confirmation_prompt = None
            self._refresh()
        return reply

    def _reply_permission_from_tui(self, reply: str) -> None:
        with self.lock:
            if self.permission_request is None:
                return
            self._permission_reply = reply
            self._permission_event.set()

    def _reply_confirmation_from_tui(self, reply: bool) -> None:
        with self.lock:
            if self.confirmation_prompt is None:
                return
            self._confirmation_reply = reply
            self._confirmation_event.set()

    def _state_for(self, name: str) -> FunctionState:
        for state in self.functions:
            if state.name == name:
                return state
        state = FunctionState(name=name)
        self.functions.append(state)
        return state

    def _refresh(self) -> None:
        if self.app and self._app_ready.is_set():
            try:
                self.app.call_from_thread(self.app.refresh_from_owner)
            except Exception:
                pass

    def _ensure_web_ui(self) -> None:
        if self.web_server:
            return
        self.web_server = RuntimeStatusServer(self)
        self.web_url = self.web_server.start()
        print(f"[Web UI] 实时状态页面: {self.web_url}", file=sys.stderr, flush=True)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "stage": self.stage,
                "function_name": self.function_name,
                "audit_type": self.audit_type,
                "runtime": self.runtime,
                "session_id": self.session_id,
                "exit_hint": self.tui_exit_hint,
                "web_url": self.web_url,
                "functions": [
                    {
                        "name": item.name,
                        "file_path": item.file_path,
                        "stage": item.stage,
                        "audit_type": item.audit_type,
                        "status": item.status,
                    }
                    for item in self.functions
                ],
                "permission_request": self.permission_request,
                "permission_session_id": self.permission_session_id,
                "confirmation_prompt": self.confirmation_prompt,
                "logs": list(self.logs),
            }


_STATUS = TerminalStatus()


def get_terminal_status() -> TerminalStatus:
    return _STATUS
