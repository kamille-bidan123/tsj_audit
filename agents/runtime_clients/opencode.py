#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opencode serve runtime client."""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode, urlparse

from pydantic import BaseModel

from agents.runtime_clients.base import BaseRuntimeClient
from utils.terminal_status import get_terminal_status


class OpenCodeRuntimeClient(BaseRuntimeClient):
    runtime = "opencode"
    _permission_prompt_lock = threading.Lock()
    _event_bus_lock = threading.Lock()
    _event_bus_threads: dict[tuple[str, str], threading.Thread] = {}
    _event_bus_subscribers: dict[tuple[str, str], list] = {}

    def run_raw(
        self,
        *,
        prompt: str,
        output_model: type[BaseModel],
        config,
        stage_name: str,
    ) -> Any:
        self._log(f"[opencode] stage={stage_name} 创建 session")
        session = self._request("POST", "/session", None, config)
        session_id = session.get("id") or session.get("data", {}).get("id")
        if not session_id:
            raise RuntimeError(f"opencode did not return a session id: {session}")
        get_terminal_status().set_runtime("opencode", session_id=session_id)
        self._log(f"[opencode] stage={stage_name} session={session_id} 发送 message")

        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": prompt}],
        }
        tool_policy = self._tool_policy(stage_name)
        if tool_policy:
            body["tools"] = tool_policy
        provider_id = (config.opencode_provider_id or "").strip()
        model_id = (config.opencode_model_id or "").strip()
        if provider_id and model_id:
            body["model"] = {
                "providerID": provider_id,
                "modelID": model_id,
            }

        stop_events = self._start_activity_listeners(session_id, stage_name=stage_name, config=config)
        try:
            response = self._request("POST", f"/session/{session_id}/message", body, config)
            self._raise_for_assistant_error(response)
            self._log_tool_parts(
                response,
                session_id=session_id,
                debug=bool(getattr(config, "debug", False)),
            )
            self._log(f"[opencode] stage={stage_name} session={session_id} 收到响应")
            return response
        finally:
            stop_events.set()

    def _request(self, method: str, path: str, body: Any, config) -> Any:
        base_url = config.opencode_base_url.rstrip("/")
        request_path = self._path_with_project_context(path)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}{request_path}",
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(  # noqa: S310 - user-configured local agent server.
                request,
                timeout=config.external_runtime_timeout_seconds,
            ) as response:
                text = response.read().decode("utf-8", errors="replace")
                return self._parse_json_response(
                    text,
                    base_url=base_url,
                    path=request_path,
                    status=response.status,
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"opencode serve returned HTTP {exc.code} for {method} {base_url}{request_path}: "
                f"{self._preview(text)}"
            ) from exc
        except urllib.error.URLError as exc:
            hint = self._connection_hint(base_url)
            raise RuntimeError(
                f"failed to call opencode serve at {base_url}: {exc}. "
                f"{hint}"
            ) from exc

    def _parse_json_response(self, text: str, *, base_url: str, path: str, status: int) -> Any:
        stripped = text.strip()
        if not stripped:
            raise RuntimeError(
                f"opencode serve returned empty response for {base_url}{path} "
                f"(HTTP {status}). Check whether opencode serve is running and whether the API path is supported."
            )
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"opencode serve returned non-JSON response for {base_url}{path} "
                f"(HTTP {status}): {self._preview(stripped)}"
            ) from exc

    def _path_with_project_context(self, path: str) -> str:
        """Bind opencode serve requests to the configured project directory."""
        separator = "&" if "?" in path else "?"
        query = urlencode({"directory": str(self.project_path)})
        return f"{path}{separator}{query}"

    def _preview(self, text: str, *, limit: int = 500) -> str:
        stripped = text.strip()
        if not stripped:
            return "<empty response body>"
        if len(stripped) > limit:
            return f"{stripped[:limit]}..."
        return stripped

    def _raise_for_assistant_error(self, response: Any) -> None:
        if not isinstance(response, dict):
            return
        info = response.get("info")
        if not isinstance(info, dict):
            return
        error = info.get("error")
        if not isinstance(error, dict):
            return

        name = error.get("name") or "Error"
        data = error.get("data") if isinstance(error.get("data"), dict) else {}
        message = data.get("message") or error.get("message") or "unknown opencode assistant error"
        response_body = data.get("responseBody")
        detail = f" responseBody={self._preview(response_body)}" if isinstance(response_body, str) else ""
        raise RuntimeError(f"opencode assistant returned {name}: {message}.{detail}")

    def _connection_hint(self, base_url: str) -> str:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        if host in {"127.0.0.1", "localhost", "::1"}:
            return (
                "Start it with `opencode serve --hostname 127.0.0.1 --port "
                f"{parsed.port or 4096}` or update opencode_base_url."
            )
        return "Start opencode serve or set opencode_base_url."

    def _log(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def _tool_policy(self, stage_name: str) -> dict[str, bool]:
        """Return explicit tool policy overrides."""
        return {
            "bash": True,
            "shell": True,
        }

    def _start_activity_listeners(self, session_id: str, *, stage_name: str, config) -> threading.Event:
        stop_event = threading.Event()
        seen: set[tuple[str, str]] = set()
        seen_permissions: set[str] = set()
        if getattr(config, "opencode_enable_event_stream", False):
            unsubscribe_events = self._subscribe_events(
                session_id,
                stage_name=stage_name,
                config=config,
                seen=seen,
                seen_permissions=seen_permissions,
            )
        else:
            self._log("[opencode:event] /event 监听已关闭，使用轮询获取 tool/permission 日志")
            unsubscribe_events = lambda: None
        poll_thread = threading.Thread(
            target=self._poll_session_messages,
            args=(session_id, stage_name, config, stop_event, seen, seen_permissions),
            daemon=True,
        )
        poll_thread.start()
        return self._activity_stop_handle(stop_event, unsubscribe_events)

    def _activity_stop_handle(self, stop_event: threading.Event, unsubscribe_events):
        class StopHandle:
            def set(self):
                unsubscribe_events()
                stop_event.set()

        return StopHandle()

    def _subscribe_events(
        self,
        session_id: str,
        *,
        stage_name: str,
        config,
        seen: set[tuple[str, str]],
        seen_permissions: set[str],
    ):
        key = self._event_bus_key(config)

        def callback(event: Any) -> None:
            self._handle_permission_event(
                event,
                session_id=session_id,
                config=config,
                seen_permissions=seen_permissions,
            )
            self._log_tool_parts(
                event,
                session_id=session_id,
                seen=seen,
                debug=bool(getattr(config, "debug", False)),
            )

        with self._event_bus_lock:
            self._event_bus_subscribers.setdefault(key, []).append(callback)
            thread = self._event_bus_threads.get(key)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(
                    target=self._run_shared_event_bus,
                    args=(key, stage_name, config),
                    daemon=True,
                )
                self._event_bus_threads[key] = thread
                thread.start()

        def unsubscribe() -> None:
            with self._event_bus_lock:
                callbacks = self._event_bus_subscribers.get(key)
                if not callbacks:
                    return
                try:
                    callbacks.remove(callback)
                except ValueError:
                    pass
                if not callbacks:
                    self._event_bus_subscribers.pop(key, None)

        return unsubscribe

    def _event_bus_key(self, config) -> tuple[str, str]:
        return (config.opencode_base_url.rstrip("/"), str(self.project_path))

    def _run_shared_event_bus(self, key: tuple[str, str], stage_name: str, config) -> None:
        base_url = config.opencode_base_url.rstrip("/")
        request = urllib.request.Request(
            f"{base_url}{self._path_with_project_context('/event')}",
            method="GET",
            headers={"Accept": "text/event-stream"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        started_logged = False
        fast_disconnects = 0
        while True:
            with self._event_bus_lock:
                if not self._event_bus_subscribers.get(key):
                    self._event_bus_threads.pop(key, None)
                    return
            try:
                connected_at = time.monotonic()
                with opener.open(request, timeout=10) as response:  # noqa: S310 - user-configured local agent server.
                    if not started_logged:
                        self._log(f"[opencode:event] stage={stage_name} shared listener 已启动")
                        started_logged = True
                    while True:
                        with self._event_bus_lock:
                            if not self._event_bus_subscribers.get(key):
                                self._event_bus_threads.pop(key, None)
                                return
                        try:
                            line = response.readline()
                        except (TimeoutError, socket.timeout):
                            continue
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if not decoded.startswith("data:"):
                            continue
                        payload = decoded.removeprefix("data:").strip()
                        if not payload:
                            continue
                        event = self._try_parse_json(payload)
                        if event is None:
                            continue
                        self._dispatch_shared_event(key, event)
                if time.monotonic() - connected_at < 3:
                    fast_disconnects += 1
                else:
                    fast_disconnects = 0
                if fast_disconnects >= 3:
                    self._log(
                        "[opencode:event] shared listener 连续快速断开，已降级为轮询日志，"
                        "不再重连 /event"
                    )
                    with self._event_bus_lock:
                        self._event_bus_threads.pop(key, None)
                    return
                threading.Event().wait(2)
            except Exception as exc:
                with self._event_bus_lock:
                    has_subscribers = bool(self._event_bus_subscribers.get(key))
                if not has_subscribers:
                    self._event_bus_threads.pop(key, None)
                    return
                fast_disconnects += 1
                if fast_disconnects >= 3:
                    self._log(
                        f"[opencode:event] shared listener 连续失败，已降级为轮询日志: {exc}"
                    )
                    with self._event_bus_lock:
                        self._event_bus_threads.pop(key, None)
                    return
                self._log(f"[opencode:event] stage={stage_name} shared listener 失败，将重连: {exc}")
                threading.Event().wait(2)

    def _dispatch_shared_event(self, key: tuple[str, str], event: Any) -> None:
        with self._event_bus_lock:
            callbacks = list(self._event_bus_subscribers.get(key) or [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as exc:
                self._log(f"[opencode:event] callback 失败: {exc}")

    def _poll_session_messages(
        self,
        session_id: str,
        stage_name: str,
        config,
        stop_event: threading.Event,
        seen: set[tuple[str, str]],
        seen_permissions: set[str],
    ) -> None:
        while not stop_event.is_set():
            try:
                messages = self._request("GET", f"/session/{session_id}/message", None, config)
                self._log_tool_parts(
                    messages,
                    session_id=session_id,
                    seen=seen,
                    debug=bool(getattr(config, "debug", False)),
                )
                permissions = self._request("GET", "/permission", None, config)
                self._handle_pending_permissions(
                    permissions,
                    session_id=session_id,
                    config=config,
                    seen_permissions=seen_permissions,
                )
            except Exception as exc:
                if not stop_event.is_set():
                    self._log(f"[opencode:poll] stage={stage_name} session={session_id} 查询失败: {exc}")
            stop_event.wait(2)

    def _try_parse_json(self, text: str) -> Any | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _log_tool_parts(
        self,
        value: Any,
        *,
        session_id: str,
        seen: set[tuple[str, str]] | None = None,
        debug: bool = False,
    ) -> None:
        if seen is None:
            seen = set()
        for part in self._iter_tool_parts(value):
            part_session = part.get("sessionID")
            if part_session and part_session != session_id:
                continue
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            status = str(state.get("status") or "unknown")
            call_id = str(part.get("callID") or part.get("id") or "unknown")
            key = (call_id, status)
            if key in seen:
                continue
            seen.add(key)

            tool = part.get("tool") or "unknown"
            title = state.get("title") or ""
            message = f"[opencode:tool] session={session_id} tool={tool} call={call_id} status={status}"
            if title:
                message += f" title={title}"
            if debug:
                input_preview = self._json_preview(state.get("input"))
                output_preview = self._preview(str(state.get("output") or ""), limit=300)
                error_preview = self._preview(str(state.get("error") or ""), limit=300)
                if input_preview and status in {"pending", "running"}:
                    message += f" input={input_preview}"
                if output_preview and status == "completed":
                    message += f" output={output_preview}"
                if error_preview and status == "error":
                    message += f" error={error_preview}"
            self._log(message)

    def _iter_tool_parts(self, value: Any):
        if isinstance(value, dict):
            if value.get("type") == "tool" and isinstance(value.get("state"), dict):
                yield value
            for item in value.values():
                yield from self._iter_tool_parts(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._iter_tool_parts(item)

    def _json_preview(self, value: Any, *, limit: int = 300) -> str:
        if value in (None, "", {}, []):
            return ""
        try:
            return self._preview(json.dumps(value, ensure_ascii=False), limit=limit)
        except TypeError:
            return self._preview(str(value), limit=limit)

    def _handle_permission_event(
        self,
        event: Any,
        *,
        session_id: str,
        config,
        seen_permissions: set[str],
    ) -> None:
        if not isinstance(event, dict) or event.get("type") != "permission.asked":
            return
        request = event.get("properties")
        if not isinstance(request, dict):
            return
        self._handle_permission_request(
            request,
            session_id=session_id,
            config=config,
            seen_permissions=seen_permissions,
        )

    def _handle_pending_permissions(
        self,
        permissions: Any,
        *,
        session_id: str,
        config,
        seen_permissions: set[str],
    ) -> None:
        if not isinstance(permissions, list):
            return
        for request in permissions:
            if isinstance(request, dict):
                self._handle_permission_request(
                    request,
                    session_id=session_id,
                    config=config,
                    seen_permissions=seen_permissions,
                )

    def _handle_permission_request(
        self,
        request: dict[str, Any],
        *,
        session_id: str,
        config,
        seen_permissions: set[str],
    ) -> None:
        permission_id = str(request.get("id") or "")
        request_session = request.get("sessionID")
        if not permission_id or request_session != session_id:
            return
        if permission_id in seen_permissions:
            return
        seen_permissions.add(permission_id)

        reply = self._ask_permission_reply(request, session_id=session_id)
        self._reply_permission(permission_id, reply, config)

    def _ask_permission_reply(self, request: dict[str, Any], *, session_id: str) -> str:
        with self._permission_prompt_lock:
            status = get_terminal_status()
            tui_reply = status.ask_permission(request, session_id=session_id)
            if tui_reply:
                return tui_reply

            status.pause_input()
            try:
                self._print_permission_prompt(request, session_id=session_id)
                if not sys.stdin.isatty():
                    self._log("[opencode:permission] 非交互式 stdin，默认拒绝权限请求")
                    return "reject"

                while True:
                    choice = input("批准本次(o) / 永久批准(a) / 拒绝(r) [r]: ").strip().lower()
                    if choice in {"", "r", "reject", "n", "no"}:
                        return "reject"
                    if choice in {"o", "once", "y", "yes"}:
                        return "once"
                    if choice in {"a", "always"}:
                        return "always"
                    print("请输入 o、a 或 r。", file=sys.stderr, flush=True)
            finally:
                status.resume_input()

    def _print_permission_prompt(self, request: dict[str, Any], *, session_id: str) -> None:
        bold = "\033[1m"
        yellow = "\033[93m"
        red = "\033[91m"
        cyan = "\033[96m"
        reset = "\033[0m"

        permission_id = request.get("id")
        permission = request.get("permission")
        patterns = request.get("patterns") or []
        metadata = request.get("metadata") or {}
        tool = request.get("tool") or {}

        print(file=sys.stderr, flush=True)
        print(f"{yellow}{bold}{'=' * 78}{reset}", file=sys.stderr, flush=True)
        print(f"{yellow}{bold}OPENCODE 权限请求：需要你确认后才会继续执行{reset}", file=sys.stderr, flush=True)
        print(f"{yellow}{bold}{'=' * 78}{reset}", file=sys.stderr, flush=True)
        print(f"{bold}Session:{reset} {session_id}", file=sys.stderr, flush=True)
        print(f"{bold}Permission ID:{reset} {permission_id}", file=sys.stderr, flush=True)
        print(f"{bold}申请权限:{reset} {red}{permission}{reset}", file=sys.stderr, flush=True)
        if patterns:
            print(f"{bold}影响范围/匹配:{reset}", file=sys.stderr, flush=True)
            for pattern in patterns:
                print(f"  - {pattern}", file=sys.stderr, flush=True)
        if tool:
            print(f"{bold}关联 Tool:{reset}", file=sys.stderr, flush=True)
            print(f"  - messageID: {tool.get('messageID')}", file=sys.stderr, flush=True)
            print(f"  - callID: {tool.get('callID')}", file=sys.stderr, flush=True)
        if metadata:
            print(f"{bold}动作详情:{reset} {cyan}{self._json_preview(metadata, limit=1000)}{reset}", file=sys.stderr, flush=True)
        print(f"{yellow}{bold}{'=' * 78}{reset}", file=sys.stderr, flush=True)

    def _reply_permission(self, permission_id: str, reply: str, config) -> None:
        try:
            result = self._request(
                "POST",
                f"/permission/{permission_id}/reply",
                {"reply": reply, "message": "handled by tsj_audit CLI"},
                config,
            )
            self._log(f"[opencode:permission] {permission_id} -> {reply}: {result}")
        except Exception as exc:
            self._log(f"[opencode:permission] 回复 {permission_id} 失败: {exc}")
