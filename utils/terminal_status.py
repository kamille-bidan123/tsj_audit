#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Textual-powered terminal UI for long-running audits."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from rich.text import Text


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


class _TuiStream:
    def __init__(self, owner: "TerminalStatus", original):
        self.owner = owner
        self.original = original
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self.owner.log(line)
        return len(text)

    def flush(self) -> None:
        self.original.flush()
        if self._buffer:
            self.owner.log(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        return self.original.isatty()


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
        Binding("o", "permission_once", "批准本次", show=False),
        Binding("a", "permission_always", "永久批准", show=False),
        Binding("r", "permission_reject", "拒绝", show=False),
        Binding("q", "noop", "运行中不可退出", show=False),
    ]

    def __init__(self, owner: "TerminalStatus", target: Callable[[], None]):
        super().__init__()
        self.owner = owner
        self.target = target
        self.functions_visible = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield RichLog(id="log", wrap=True, markup=True)
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
        sys.stderr = _TuiStream(self.owner, old_stderr)
        try:
            self.target()
        except BaseException as exc:
            self.owner._target_error = exc
            self.owner.log(f"[bold red]运行失败:[/bold red] {exc!r}")
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.call_from_thread(self.exit)

    def action_toggle_functions(self) -> None:
        self.functions_visible = not self.functions_visible
        table = self.query_one("#functions", DataTable)
        table.display = self.functions_visible
        if self.functions_visible:
            table.focus()

    def action_permission_once(self) -> None:
        self.owner._reply_permission_from_tui("once")

    def action_permission_always(self) -> None:
        self.owner._reply_permission_from_tui("always")

    def action_permission_reject(self) -> None:
        self.owner._reply_permission_from_tui("reject")

    def action_noop(self) -> None:
        self.notify("审计正在运行，完成后会自动退出。", severity="warning")

    def refresh_from_owner(self) -> None:
        self._refresh_all()

    def write_log(self, line: str) -> None:
        log = self.query_one("#log", RichLog)
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
            "[dim]g 展开/收起，鼠标滚动函数表[/dim]"
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
        self.enabled = bool(_TEXTUAL_AVAILABLE and sys.stderr.isatty() and sys.stdin.isatty())
        self.app: Optional[AuditStatusApp] = None
        self.lock = threading.RLock()
        self._app_ready = threading.Event()
        self._target_error: BaseException | None = None
        self.stage = "启动"
        self.function_name = "-"
        self.audit_type = "-"
        self.runtime = "-"
        self.session_id = "-"
        self.functions: list[FunctionState] = []
        self.permission_request: dict[str, Any] | None = None
        self.permission_session_id = "-"
        self._permission_event = threading.Event()
        self._permission_reply = "reject"

    def can_run_tui(self) -> bool:
        return self.enabled

    def run_with(self, target: Callable[[], None]) -> None:
        if not self.enabled:
            target()
            return
        self._target_error = None
        self.app = AuditStatusApp(self, target)
        try:
            self.app.run()
        finally:
            self.app = None
            self._app_ready.clear()
        if self._target_error is not None:
            raise self._target_error

    def start(self) -> None:
        if self.app:
            self._refresh()

    def stop(self) -> None:
        if self.app:
            try:
                self.app.call_from_thread(self.app.exit)
            except Exception:
                pass

    def pause_input(self) -> None:
        # Textual owns input; permission prompts are handled by key bindings.
        return

    def resume_input(self) -> None:
        return

    def log(self, line: str) -> None:
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
        if not self.app:
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

    def _reply_permission_from_tui(self, reply: str) -> None:
        with self.lock:
            if self.permission_request is None:
                return
            self._permission_reply = reply
            self._permission_event.set()

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


_STATUS = TerminalStatus()


def get_terminal_status() -> TerminalStatus:
    return _STATUS
