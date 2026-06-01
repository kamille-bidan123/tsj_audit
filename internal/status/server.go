package status

import (
	"encoding/json"
	"net/http"
)

func Handler(state *Status) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(statusHTML))
	})
	mux.HandleFunc("/api/status", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(state.Snapshot())
	})
	mux.HandleFunc("/api/confirm", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var request struct {
			Answer bool `json:"answer"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		state.SetConfirmationAnswer(request.Answer)
		w.WriteHeader(http.StatusOK)
	})
	mux.HandleFunc("/api/permission", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var request struct {
			Reply string `json:"reply"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		switch request.Reply {
		case "once", "always", "reject":
			state.SetPermissionReply(request.Reply)
			w.WriteHeader(http.StatusOK)
		default:
			http.Error(w, "invalid permission reply", http.StatusBadRequest)
		}
	})
	return mux
}

const statusHTML = `<!doctype html>
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
      min-height: 100vh;
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
    .shell { min-height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding: 24px 24px 16px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(250,251,248,.88));
      backdrop-filter: blur(16px);
      position: sticky;
      top: 0;
      z-index: 2;
      box-shadow: 0 1px 0 rgba(255,255,255,.75);
    }
    .brand-row { display: flex; align-items: center; gap: 11px; }
    .mark {
      width: 32px;
      height: 32px;
      border-radius: 7px;
      display: grid;
      place-items: center;
      color: #fff;
      background: var(--ink);
      box-shadow: inset 0 -8px 16px rgba(255,255,255,.08);
      font: 700 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    h1 { margin: 0; font-size: 20px; line-height: 1.2; font-weight: 720; }
    .subline { margin-top: 6px; color: var(--muted); font-size: 13px; }
    .status-strip { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; max-width: 820px; }
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
      box-shadow: 0 1px 2px rgba(20,27,26,.04);
    }
    .pill strong { color: var(--muted); font-weight: 650; text-transform: uppercase; font-size: 10px; letter-spacing: .04em; }
    .pill span { max-width: 260px; overflow: hidden; text-overflow: ellipsis; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 440px); min-height: 0; }
    .log-pane { min-width: 0; display: grid; grid-template-rows: auto auto 1fr; border-right: 1px solid var(--line); }
    .toolbar, .side-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 13px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-soft);
    }
    .toolbar h2, .side-head h2 { margin: 0; font-size: 14px; font-weight: 700; }
    .toolbar-meta { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 12px; }
    .metrics { display: grid; grid-template-columns: repeat(3, 1fr); border-bottom: 1px solid var(--line); background: #fff; }
    .metric { padding: 13px 16px; border-right: 1px solid var(--line); }
    .metric:last-child { border-right: 0; }
    .metric span { display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; font-weight: 700; }
    .metric strong { display: block; margin-top: 4px; font-size: 20px; line-height: 1.1; min-height: 22px; }
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
    button:hover { border-color: var(--line-strong); transform: translateY(-1px); }
    button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    button.danger { color: var(--danger); border-color: #e3b7b2; }
    .log {
      overflow: auto;
      padding: 16px 18px 24px;
      background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,0) 120px), #101719;
      color: #dce7e4;
      font: 12.5px/1.52 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      min-height: 420px;
    }
    .log-line { white-space: pre-wrap; overflow-wrap: anywhere; padding: 2px 0 2px 12px; border-left: 2px solid transparent; }
    .log-line.warn { color: #ffd58a; border-left-color: #d79a2b; background: rgba(215,154,43,.08); }
    .log-line.error { color: #ffb4aa; border-left-color: #d66557; background: rgba(214,101,87,.08); }
    .empty { color: #8ba29c; padding: 18px 12px; }
    .side { min-width: 0; display: grid; grid-template-rows: auto auto auto 1fr; background: var(--panel); }
    .prompt {
      display: none;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: #fff6e2;
      box-shadow: var(--shadow);
    }
    .prompt.active { display: block; }
    .prompt h3 { margin: 0 0 8px; font-size: 14px; color: var(--amber); }
    .prompt pre {
      margin: 0 0 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--ink);
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .prompt-actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .details { padding: 16px 18px; border-bottom: 1px solid var(--line); display: grid; gap: 12px; }
    .row { display: grid; grid-template-columns: 108px minmax(0, 1fr); gap: 10px; font-size: 13px; }
    .row span:first-child { color: var(--muted); font-weight: 650; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
    .function-list { padding: 16px 18px; overflow: auto; }
    .function-list h3 { margin: 0 0 12px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
    .functions { display: grid; gap: 8px; }
    .function-item {
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 7px;
      padding: 10px 11px;
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .function-item.running { border-color: #8fc7bf; background: #eefaf7; }
    .function-item.done { border-color: #b7d8b9; background: #f1faef; }
    .function-item.skipped { border-color: #d8c8a8; background: #fbf6e8; }
    .function-item strong { display: block; margin-bottom: 4px; color: var(--accent-ink); }
    .function-meta { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .function-status { display: inline-flex; margin-top: 8px; padding: 2px 7px; border-radius: 999px; background: #fff; border: 1px solid var(--line); color: var(--muted); font-weight: 700; text-transform: uppercase; font-size: 10px; }
    @media (max-width: 900px) {
      header { grid-template-columns: 1fr; align-items: start; }
      .status-strip { justify-content: flex-start; }
      main { grid-template-columns: 1fr; }
      .log-pane { border-right: 0; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <div class="brand-row"><div class="mark">TSJ</div><div><h1>TSJ Audit Runtime</h1><div class="subline">实时审计状态、日志和 runtime permission 控制台</div></div></div>
      </div>
      <div class="status-strip">
        <div class="pill"><strong>stage</strong><span id="pill-stage">-</span></div>
        <div class="pill"><strong>function</strong><span id="pill-function">-</span></div>
        <div class="pill"><strong>audit</strong><span id="pill-audit">-</span></div>
        <div class="pill"><strong>runtime</strong><span id="pill-runtime">-</span></div>
      </div>
    </header>
    <main>
      <section class="log-pane">
        <div class="toolbar">
          <h2>Runtime Log</h2>
          <div class="toolbar-meta"><span id="updated">waiting</span><button id="follow">Follow</button></div>
        </div>
        <div class="metrics">
          <div class="metric"><span>Stage</span><strong id="metric-stage">-</strong></div>
          <div class="metric"><span>Function</span><strong id="metric-function">-</strong></div>
          <div class="metric"><span>Log lines</span><strong id="metric-logs">0</strong></div>
        </div>
        <div class="log" id="log"><div class="empty">等待运行时日志...</div></div>
      </section>
      <aside class="side">
        <div class="side-head"><h2>Controls</h2><button id="refresh">Refresh</button></div>
        <div class="prompt" id="confirm-box">
          <h3>需要确认</h3>
          <pre id="confirm-text"></pre>
          <div class="prompt-actions"><button class="primary" data-confirm="true">Continue</button><button class="danger" data-confirm="false">Stop</button></div>
        </div>
        <div class="prompt" id="permission-box">
          <h3>OpenCode 权限请求</h3>
          <pre id="permission-text"></pre>
          <div class="prompt-actions"><button class="primary" data-permission="once">批准本次</button><button data-permission="always">永久批准</button><button class="danger" data-permission="reject">拒绝</button></div>
        </div>
        <div class="details">
          <div class="row"><span>Runtime</span><span class="mono" id="detail-runtime">-</span></div>
          <div class="row"><span>Session</span><span class="mono" id="detail-session">-</span></div>
          <div class="row"><span>Function</span><span class="mono" id="detail-function">-</span></div>
          <div class="row"><span>Audit Type</span><span class="mono" id="detail-audit">-</span></div>
        </div>
        <div class="function-list">
          <h3>Functions</h3>
          <div class="functions" id="functions"></div>
        </div>
      </aside>
    </main>
  </div>
  <script>
    const state = { follow: true, lastLogLength: 0 };
    const $ = id => document.getElementById(id);
    function value(v) { return v === undefined || v === null || v === "" ? "-" : String(v); }
    function classify(line) {
      const text = String(line || "");
      if (/error|failed|失败|异常/i.test(text)) return "error";
      if (/warn|permission|确认|批准|fallback|降级/i.test(text)) return "warn";
      return "";
    }
    function renderLog(logs) {
      const box = $("log");
      const lines = Array.isArray(logs) ? logs : [];
      if (!lines.length) {
        box.innerHTML = '<div class="empty">等待运行时日志...</div>';
        return;
      }
      box.innerHTML = lines.map(line => '<div class="log-line '+classify(line)+'">'+escapeHtml(line)+'</div>').join("");
      if (state.follow) box.scrollTop = box.scrollHeight;
    }
    function renderFunctions(functions) {
      const box = $("functions");
      const items = Array.isArray(functions) ? functions : [];
      if (!items.length) {
        box.innerHTML = '<div class="function-item"><strong>Idle</strong><div class="function-meta">等待入口函数发现...</div></div>';
        return;
      }
      box.innerHTML = items.map(item => {
        const status = value(item.status).toLowerCase();
        const meta = [item.file, item.skill].filter(Boolean).join(" · ");
        return '<div class="function-item '+escapeHtml(status)+'"><strong>'+escapeHtml(item.name || "-")+'</strong><div class="function-meta">'+escapeHtml(meta || "-")+'</div><span class="function-status">'+escapeHtml(status)+'</span></div>';
      }).join("");
    }
    function renderPermission(request) {
      const box = $("permission-box");
      if (!request) { box.classList.remove("active"); return; }
      box.classList.add("active");
      $("permission-text").textContent = JSON.stringify(request, null, 2);
    }
    function renderConfirm(prompt) {
      const box = $("confirm-box");
      if (!prompt) { box.classList.remove("active"); return; }
      box.classList.add("active");
      $("confirm-text").textContent = prompt;
    }
    async function postJSON(path, body) {
      await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      await refresh();
    }
    async function refresh() {
      const response = await fetch("/api/status", { cache: "no-store" });
      const data = await response.json();
      $("pill-stage").textContent = value(data.stage);
      $("pill-function").textContent = value(data.function_name);
      $("pill-audit").textContent = value(data.audit_type);
      $("pill-runtime").textContent = value(data.runtime);
      $("metric-stage").textContent = value(data.stage);
      $("metric-function").textContent = value(data.function_name);
      $("metric-logs").textContent = Array.isArray(data.logs) ? data.logs.length : 0;
      $("detail-runtime").textContent = value(data.runtime);
      $("detail-session").textContent = value(data.session_id);
      $("detail-function").textContent = value(data.function_name);
      $("detail-audit").textContent = value(data.audit_type);
      $("updated").textContent = new Date().toLocaleTimeString();
      renderLog(data.logs);
      renderFunctions(data.functions);
      renderConfirm(data.confirmation_prompt);
      renderPermission(data.permission_request);
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[ch]));
    }
    $("refresh").addEventListener("click", refresh);
    $("follow").addEventListener("click", () => {
      state.follow = !state.follow;
      $("follow").textContent = state.follow ? "Follow" : "Paused";
    });
    document.querySelectorAll("[data-confirm]").forEach(button => button.addEventListener("click", () => postJSON("/api/confirm", { answer: button.dataset.confirm === "true" })));
    document.querySelectorAll("[data-permission]").forEach(button => button.addEventListener("click", () => postJSON("/api/permission", { reply: button.dataset.permission })));
    $("log").addEventListener("scroll", event => {
      const el = event.currentTarget;
      state.follow = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      $("follow").textContent = state.follow ? "Follow" : "Paused";
    });
    refresh();
    setInterval(refresh, 1200);
  </script>
</body>
</html>`
