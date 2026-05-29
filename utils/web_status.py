#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small local web UI for live audit status."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TSJ Audit Runtime</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f5f2;
      --panel: #ffffff;
      --panel-soft: #fafbf8;
      --ink: #182025;
      --muted: #657077;
      --line: #d6ddd6;
      --line-strong: #bbc7c0;
      --accent: #06746f;
      --accent-ink: #034f4b;
      --amber: #9b6200;
      --danger: #b42318;
      --blue: #315f92;
      --soft: #e7f3ef;
      --shadow: 0 18px 50px rgba(27, 37, 35, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0 0 auto 0;
      height: 7px;
      background: linear-gradient(90deg, var(--accent), var(--blue) 52%, #8b5b13);
      z-index: 5;
    }
    .shell {
      min-height: 100svh;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding: 24px 24px 16px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(250, 251, 248, 0.88));
      backdrop-filter: blur(16px);
      position: sticky;
      top: 0;
      z-index: 2;
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.75);
    }
    .brand-row {
      display: flex;
      align-items: center;
      gap: 11px;
    }
    .mark {
      width: 32px;
      height: 32px;
      border-radius: 7px;
      display: grid;
      place-items: center;
      color: #fff;
      background: var(--ink);
      box-shadow: inset 0 -8px 16px rgba(255,255,255,0.08);
      font: 700 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 720;
    }
    .subline {
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .status-strip {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      max-width: 760px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 32px;
      padding: 0 11px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      font-size: 12px;
      white-space: nowrap;
      box-shadow: 0 1px 2px rgba(20, 27, 26, 0.04);
    }
    .pill strong {
      color: var(--muted);
      font-weight: 650;
      text-transform: uppercase;
      font-size: 10px;
      letter-spacing: .04em;
    }
    .pill span {
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(380px, 440px);
      min-height: 0;
    }
    .log-pane {
      min-width: 0;
      display: grid;
      grid-template-rows: auto 1fr;
      border-right: 1px solid var(--line);
    }
    .toolbar, .side-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-soft);
    }
    .toolbar h2, .side-head h2 {
      margin: 0;
      font-size: 14px;
      font-weight: 700;
    }
    .toolbar-meta {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }
    .metric {
      padding: 13px 16px;
      border-right: 1px solid var(--line);
    }
    .metric:last-child { border-right: 0; }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .04em;
      font-weight: 700;
    }
    .metric strong {
      display: block;
      margin-top: 4px;
      font-size: 20px;
      line-height: 1.1;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      min-height: 32px;
      padding: 0 12px;
      border-radius: 6px;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
      transition: background .15s ease, border-color .15s ease, color .15s ease, transform .15s ease;
    }
    button:hover {
      border-color: var(--line-strong);
      transform: translateY(-1px);
    }
    button.primary {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    button.danger {
      color: var(--danger);
      border-color: #e3b7b2;
    }
    .log {
      overflow: auto;
      padding: 16px 18px 24px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0) 120px),
        #101719;
      color: #dce7e4;
      font: 12.5px/1.52 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      min-height: 360px;
    }
    .log-line {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      padding: 2px 0 2px 12px;
      border-left: 2px solid transparent;
    }
    .log-line.stderr {
      color: #ffb4aa;
      border-left-color: #d66557;
      background: rgba(214, 101, 87, 0.08);
    }
    .side {
      min-width: 0;
      display: grid;
      grid-template-rows: auto auto auto 1fr;
      background: var(--panel);
    }
    .prompt {
      display: none;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: #fff6e2;
      box-shadow: var(--shadow);
    }
    .prompt.active { display: block; }
    .prompt h3 {
      margin: 0 0 8px;
      font-size: 14px;
      color: var(--amber);
    }
    .prompt pre {
      margin: 0 0 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--ink);
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .table-wrap { overflow: auto; min-height: 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
    }
    th, td {
      text-align: left;
      padding: 10px 13px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    td {
      overflow-wrap: anywhere;
    }
    tr:hover td { background: #f8faf7; }
    tr.running td {
      background: var(--soft);
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .badge {
      display: inline-block;
      min-width: 58px;
      padding: 3px 7px;
      border-radius: 999px;
      background: #eef1ed;
      color: var(--muted);
      font-size: 11px;
      text-align: center;
      font-weight: 700;
    }
    tr.running .badge { background: #d7efeb; color: var(--accent-ink); }
    tr.done .badge { background: #edf7e8; color: #427b28; }
    .empty {
      padding: 28px 18px;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 980px) {
      header { grid-template-columns: 1fr; align-items: start; }
      .status-strip { justify-content: flex-start; }
      main { grid-template-columns: 1fr; }
      .log-pane { border-right: 0; border-bottom: 1px solid var(--line); }
      .side { min-height: 420px; }
      .metrics { grid-template-columns: 1fr 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <div class="brand-row">
          <div class="mark">TSJ</div>
          <div>
            <h1>Audit Runtime</h1>
            <div class="subline" id="exitHint">正在连接运行时状态...</div>
          </div>
        </div>
      </div>
      <div class="status-strip" id="statusStrip"></div>
    </header>
    <main>
      <section class="log-pane">
        <div class="toolbar">
          <div>
            <h2>实时日志</h2>
            <div class="toolbar-meta" id="logMeta">等待第一条日志</div>
          </div>
          <button id="followButton" class="primary" type="button">跟随开启</button>
        </div>
        <div class="log" id="log"></div>
      </section>
      <aside class="side">
        <section class="prompt" id="prompt"></section>
        <section class="metrics">
          <div class="metric"><span>总数</span><strong id="metricTotal">0</strong></div>
          <div class="metric"><span>运行</span><strong id="metricRunning">0</strong></div>
          <div class="metric"><span>完成</span><strong id="metricDone">0</strong></div>
        </section>
        <div class="side-head">
          <h2>函数进度</h2>
          <button id="refreshButton" type="button">刷新</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>状态</th>
                <th>函数</th>
                <th>阶段</th>
                <th>类型</th>
              </tr>
            </thead>
            <tbody id="functions"></tbody>
          </table>
        </div>
      </aside>
    </main>
  </div>
  <script>
    const logEl = document.getElementById("log");
    const statusStrip = document.getElementById("statusStrip");
    const functionsEl = document.getElementById("functions");
    const promptEl = document.getElementById("prompt");
    const exitHint = document.getElementById("exitHint");
    const followButton = document.getElementById("followButton");
    const refreshButton = document.getElementById("refreshButton");
    const logMeta = document.getElementById("logMeta");
    const metricTotal = document.getElementById("metricTotal");
    const metricRunning = document.getElementById("metricRunning");
    const metricDone = document.getElementById("metricDone");
    let follow = true;
    let renderedSeq = 0;

    function text(value) {
      return value === null || value === undefined || value === "" ? "-" : String(value);
    }

    function post(path, payload) {
      return fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
    }

    function renderStatus(data) {
      const items = [
        ["阶段", data.stage],
        ["函数", data.function_name],
        ["类型", data.audit_type],
        ["runtime", data.runtime],
        ["session", data.session_id]
      ];
      statusStrip.innerHTML = "";
      for (const [label, value] of items) {
        const pill = document.createElement("div");
        pill.className = "pill";
        pill.innerHTML = `<strong>${label}</strong><span></span>`;
        pill.querySelector("span").textContent = text(value);
        pill.title = text(value);
        statusStrip.appendChild(pill);
      }
      exitHint.textContent = text(data.exit_hint);
    }

    function renderLogs(logs) {
      for (const item of logs) {
        if (item.seq <= renderedSeq) continue;
        const line = document.createElement("div");
        line.className = `log-line ${item.stream === "stderr" ? "stderr" : ""}`;
        line.textContent = item.line;
        line.title = item.time || "";
        logEl.appendChild(line);
        renderedSeq = item.seq;
      }
      while (logEl.children.length > 1200) {
        logEl.removeChild(logEl.firstChild);
      }
      logMeta.textContent = renderedSeq > 0 ? `已接收 ${renderedSeq} 行` : "等待第一条日志";
      if (follow) logEl.scrollTop = logEl.scrollHeight;
    }

    function renderFunctions(functions) {
      functionsEl.innerHTML = "";
      const total = functions.length;
      const running = functions.filter((item) => item.status === "running").length;
      const done = functions.filter((item) => item.status === "done").length;
      metricTotal.textContent = total;
      metricRunning.textContent = running;
      metricDone.textContent = done;
      if (total === 0) {
        const row = document.createElement("tr");
        row.innerHTML = `<td colspan="4"><div class="empty">等待入口发现结果</div></td>`;
        functionsEl.appendChild(row);
        return;
      }
      for (const item of functions) {
        const row = document.createElement("tr");
        row.className = item.status || "pending";
        row.innerHTML = `
          <td><span class="badge"></span></td>
          <td></td>
          <td></td>
          <td></td>
        `;
        row.children[0].querySelector(".badge").textContent = text(item.status || "pending");
        row.children[1].textContent = text(item.name);
        row.children[2].textContent = text(item.stage);
        row.children[3].textContent = text(item.audit_type);
        row.title = text(item.file_path);
        functionsEl.appendChild(row);
      }
    }

    function renderPrompt(data) {
      const confirmation = data.confirmation_prompt;
      const permission = data.permission_request;
      if (confirmation) {
        promptEl.className = "prompt active";
        promptEl.innerHTML = `
          <h3>需要确认</h3>
          <pre></pre>
          <div class="actions">
            <button class="primary" data-confirm="true" type="button">继续</button>
            <button class="danger" data-confirm="false" type="button">终止</button>
          </div>
        `;
        promptEl.querySelector("pre").textContent = confirmation;
        promptEl.querySelector("[data-confirm='true']").onclick = () => post("/api/confirmation", {reply: true});
        promptEl.querySelector("[data-confirm='false']").onclick = () => post("/api/confirmation", {reply: false});
        return;
      }
      if (permission) {
        const detail = [
          `Session: ${text(data.permission_session_id)}`,
          `Permission ID: ${text(permission.id)}`,
          `申请权限: ${text(permission.permission)}`,
          `影响范围: ${text((permission.patterns || []).join(", "))}`,
          `动作详情: ${JSON.stringify(permission.metadata || {}, null, 2)}`
        ].join("\\n");
        promptEl.className = "prompt active";
        promptEl.innerHTML = `
          <h3>OPENCODE 权限请求</h3>
          <pre></pre>
          <div class="actions">
            <button class="primary" data-reply="once" type="button">批准本次</button>
            <button data-reply="always" type="button">永久批准</button>
            <button class="danger" data-reply="reject" type="button">拒绝</button>
          </div>
        `;
        promptEl.querySelector("pre").textContent = detail;
        for (const button of promptEl.querySelectorAll("[data-reply]")) {
          button.onclick = () => post("/api/permission", {reply: button.dataset.reply});
        }
        return;
      }
      promptEl.className = "prompt";
      promptEl.innerHTML = "";
    }

    async function refresh() {
      try {
        const response = await fetch(`/api/status?after=${renderedSeq}`, {cache: "no-store"});
        const data = await response.json();
        renderStatus(data);
        renderLogs(data.logs || []);
        renderFunctions(data.functions || []);
        renderPrompt(data);
      } catch (error) {
        exitHint.textContent = "状态服务暂时不可用";
      }
    }

    followButton.onclick = () => {
      follow = !follow;
      followButton.textContent = follow ? "跟随开启" : "跟随关闭";
      followButton.className = follow ? "primary" : "";
      if (follow) logEl.scrollTop = logEl.scrollHeight;
    };
    logEl.addEventListener("wheel", () => {
      follow = false;
      followButton.textContent = "跟随关闭";
      followButton.className = "";
    }, {passive: true});
    refreshButton.onclick = refresh;
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""


class RuntimeStatusServer:
    """Threaded HTTP server that exposes a TerminalStatus snapshot."""

    def __init__(self, owner: Any, *, host: str = "127.0.0.1", preferred_port: int = 8765) -> None:
        self.owner = owner
        self.host = host
        self.preferred_port = preferred_port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.url = ""

    def start(self) -> str:
        if self.httpd is not None:
            return self.url

        handler = self._handler_class()
        last_error: OSError | None = None
        for port in range(self.preferred_port, self.preferred_port + 50):
            try:
                self.httpd = ThreadingHTTPServer((self.host, port), handler)
                self.url = f"http://{self.host}:{port}/"
                break
            except OSError as exc:
                last_error = exc
        if self.httpd is None:
            raise RuntimeError(f"无法启动 Web UI 服务: {last_error}")

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def stop(self) -> None:
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self.thread = None

    def _handler_class(self):
        owner = self.owner

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send_text(HTML_PAGE, "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/status":
                    self._send_json(owner.snapshot())
                    return
                self.send_error(404)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                payload = self._read_json()
                if parsed.path == "/api/permission":
                    reply = str(payload.get("reply") or "reject")
                    if reply not in {"once", "always", "reject"}:
                        reply = "reject"
                    owner._reply_permission_from_tui(reply)
                    self._send_json({"ok": True})
                    return
                if parsed.path == "/api/confirmation":
                    owner._reply_confirmation_from_tui(bool(payload.get("reply")))
                    self._send_json({"ok": True})
                    return
                self.send_error(404)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0:
                    return {}
                data = self.rfile.read(length)
                try:
                    parsed = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return {}
                return parsed if isinstance(parsed, dict) else {}

            def _send_json(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_text(self, text: str, content_type: str) -> None:
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
