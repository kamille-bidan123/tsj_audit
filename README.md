# TSJ Audit

TSJ Audit 是一个面向代码审计的多阶段 AI 工具。它从攻击面入口函数开始，先做代码路径追踪，再按漏洞类型逐类审计，最后可选生成 Exploit/PoC 验证结果。

## Go 重构分支

当前 `go-refactor` 分支以 Go CLI 作为主入口：

```bash
go run ./cmd/tsj-audit --help
```

本地 mock smoke 示例：

```bash
GOCACHE="$PWD/.gocache" go run ./cmd/tsj-audit \
  --config /path/to/empty.env \
  --agent-runtime mock \
  --entry /path/to/entries.json \
  --audit-types path_traversal \
  --output-dir /tmp/tsj-audit-go-output
```

Go 重构状态、已支持能力和已知缺口见 `docs/go_refactor.md`。

Go 重构验证：

```bash
GOCACHE="$PWD/.gocache" go run ./cmd/verify-go-refactor
```

当前推荐的使用方式是通过 Go CLI 的 `--attack-surface-skill` 指定一个攻击面 skill，让工具自动发现入口函数并完成后续审计。也可以使用 `--scan` 指定扫描脚本，或使用 `--entry` 指定 EntrySpec JSON 作为入口。

内置 `civetweb_audit` 和 `ioctl_audit` 已有 Go 原生扫描器。`--attack-surface-skill civetweb_audit`、`--attack-surface-skill ioctl_audit`、`--scan scripts/scan.py` 和 `--scan scripts/scan_ioctl.py` 都会走 Go 原生扫描；其他自定义 skill 仍可通过自带 `scripts/scan.py` 兼容路径或 runtime-backed discovery 发现入口。

## 审计流程

1. Entry Discovery 阶段
   - 使用 `--attack-surface-skill` 时启用。
   - Discovery Agent 注入指定攻击面 skill，输出 `{"functions": EntrySpec[]}`。
   - 结果会保存到 `output/discovered_functions.json`，并交给 Trace 阶段继续处理。

2. Trace 阶段
   - JSON 输入必须是 `EntrySpec` 列表。
   - Trace Agent 先让 runtime 根据入口描述和源码补齐 `FunctionInfo`，再根据 skill 中的外部输入知识生成代码逻辑说明和 `code_map`。

3. Audit 阶段
   - 每个漏洞类型仍然单独开启一次对话。
   - 每次对话可以输出多个 finding，最终合并为多个 `AuditResult`。
   - 漏洞类型来自 `audit_specs/*.yaml`。

4. Fallback Audit 阶段
   - 默认关闭。
   - 显式开启后，在所有正常注册漏洞类型审计完成后，额外开启一次兜底审计。
   - 兜底类型不是 YAML 中注册的正常类型，运行时动态创建，用于审计已有漏洞类型以外的安全问题。

5. Exploit 阶段
   - 默认开启，可用 `--disable-exploit` 关闭。
   - 对高/中置信度的正常审计结果生成 PoC。
   - Exploit Agent 同样会注入 Function Skill 和攻击面相关 PoC 知识。

## 快速开始

使用攻击面 skill 自动发现入口并审计：

```bash
go run ./cmd/tsj-audit \
  --project-path /path/to/project \
  --attack-surface-skill civetweb_audit \
  --output-dir output
```

使用扫描脚本作为入口：

```bash
go run ./cmd/tsj-audit \
  --project-path /path/to/project \
  --scan scripts/scan.py \
  --output-dir output
```

只运行 Go 原生入口扫描并输出 EntrySpec JSON：

```bash
go run ./cmd/scan --project-path /path/to/project --skill civetweb_audit
go run ./cmd/scan --project-path /path/to/project --skill ioctl_audit
```

使用 EntrySpec JSON 作为入口：

```bash
go run ./cmd/tsj-audit \
  --project-path /path/to/project \
  --entry entries.json \
  --output-dir output
```

断点续审：

```bash
go run ./cmd/tsj-audit --resume --output-dir output --entry entries.json
```

开启兜底审计：

```bash
go run ./cmd/tsj-audit \
  --project-path /path/to/project \
  --attack-surface-skill civetweb_audit \
  --enable-fallback-audit
```

`--scan`、`--entry` 和 `--attack-surface-skill` 互斥。一次审计应选择一种入口发现方式。

## 配置

配置优先级从高到低：

1. 命令行参数
2. `--config` 指定的 `.env` 风格配置文件
3. 当前目录或用户主目录下的 `.env`
4. 代码默认值

显式指定配置文件：

```bash
go run ./cmd/tsj-audit --config configs/opencode.env --help
```

常用配置项：

```env
agent_runtime = "codex"
opencode_base_url = "http://127.0.0.1:4096"
opencode_provider_id = ""
opencode_model_id = ""
opencode_structured_output_mode = "auto"
opencode_require_prompt_fallback_confirmation = true
opencode_inject_project_config = true
opencode_config_path = "opencode.json"
external_runtime_timeout_seconds = 1800

project_path = "."
output_dir = "output"
scan = ""
entry = ""
attack_surface_skill = ""

disable_exploit = false
enable_fallback_audit = false
audit_types = []
debug = false
resume = false

target_base_url = "http://localhost:8081"
```

`agent_runtime` 支持：

- `codex`
- `opencode`
- `claudecode`

Entry Discovery、Trace、Audit、Exploit 都通过同一套 runtime client 接口创建，因此三个 runtime 都可以参与完整流程。

当 `agent_runtime = "opencode"` 时，启动后会先做一次结构化输出 demo 探测：

- 当前模型支持 `format=json_schema`：后续直接使用 opencode 结构化输出。
- 当前模型不支持 `format=json_schema`：工具不会自动切换 thinking mode 或 variant；会退回 prompt JSON，并在日志和状态页面中输出警告；默认需要在状态页面确认后才继续。

thinking mode 的开启/关闭由使用者在 opencode/provider 配置中自行管理。工具只测试当前配置是否支持 `json_schema`。

高级 opencode 调试开关：

```env
opencode_enable_event_stream = false
```

Go 版会在每个 opencode 会话期间轮询 `/permission` 并通过状态页面暴露权限请求；开启 `opencode_enable_event_stream = true` 后还会订阅 `/event` SSE，记录 tool 事件摘要并处理 permission 事件。

`opencode_inject_project_config = true` 时，Go 版会在审计启动前合并写入待审计项目目录下的官方 `opencode.json` 配置。`opencode_config_path` 使用相对路径时会相对 `project_path` 解析；默认值会写入 `project_path/opencode.json`。

- `permission.bash` 允许读源码、搜索和运行内置扫描脚本，其它 bash 继续 ask。
- `permission.external_directory` 自动允许当前 `project_path` 源码目录。
- `permission.edit` 默认 deny；如果已有配置显式设置了 edit，会保留已有值。

如果 `opencode serve` 已经启动，建议重启一次 `opencode serve`，确保新写入的 `opencode.json` 被加载。

## 运行时 Web 界面

运行 `go run ./cmd/tsj-audit ...` 时，工具会保留普通命令行日志输出，并默认尝试启动本地实时状态页面：

```text
[Web UI] status page: http://127.0.0.1:8765
```

如果 `8765` 已被占用，命令行会输出警告并继续执行审计。浏览器页面提供运行时状态能力：

- 实时日志，包括 opencode tool call、permission、阶段输出；命令行仍同步显示。
- 当前阶段、当前审计函数、当前漏洞类型、runtime 和 session。
- 日志自动跟随开关；手动滚动日志后会暂停跟随。
- opencode 触发 write/edit/patch 等权限请求时，可通过页面提交 `once`、`always` 或 `reject`。
- prompt JSON fallback 需要确认时，可在页面中继续或终止。
- 异常退出时错误会打印到命令行；Go 版不再生成旧 Textual TUI 的 `tui_error.log`。

最终审计报告仍由现有 HTML 导出流程生成；运行时 Web 页面只用于替代旧的 Textual TUI。

## 扩展管理界面

可以启动本地 Web 管理台维护两个可扩展项：

```bash
go run ./cmd/manage-extensions --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765/` 后可以：

- 管理 `skills/attack_surface/*/SKILL.md`：新建、编辑、删除攻击面 skill。
- 管理 `skills/*/SKILL.md`：新建、编辑、删除一般 skill，自动排除 `skills/attack_surface`。
- 为攻击面 skill 配置 `required_audit_types`，绑定该攻击面必审的漏洞类型。
- 管理 `audit_specs/*.yaml`：新建、编辑、删除漏洞类型 YAML。
- 修改会直接写入当前仓库文件。

删除 skill 时，如果该 skill 目录里还有脚本或参考资料子文件，界面会拒绝删除，避免误删扫描脚本。

## 攻击面 Skill

攻击面 skill 是新流程的核心输入。一个 skill 应覆盖从入口发现到漏洞利用的完整知识，不再需要额外传 `user hint`。

skill 的 frontmatter 可以绑定该攻击面一定要审计的漏洞类型：

```yaml
---
name: civetweb_audit
description: CivetWeb HTTP/WebSocket attack surface
required_audit_types:
  - command_injection
  - path_traversal
---
```

审计类型选择规则：

- `required_audit_types`：攻击面 skill 绑定的必审类型，始终启用。
- `.env audit_types`：额外显式启用的类型，会追加到 skill 绑定类型之后。
- `FunctionInfo` 不再决定审计类型；Entry Discovery 只负责发现入口函数。
- 没有任何类型被选中时，正常 Audit 阶段不会运行；如果开启 `enable_fallback_audit`，仍会运行兜底审计。

必需内容：

1. 攻击面发现知识
   - 可以是文字描述，例如接口注册逻辑、框架路由规则、回调绑定方式。
   - 也可以附带扫描脚本作为子文件，例如 `skills/attack_surface/civetweb_audit/scripts/scan.py`。

2. 外部输入知识
   - 描述外部输入从哪些 API、参数、请求体、Header、WebSocket 消息或 RPC 字段进入代码。
   - Trace 和 Audit 阶段会用它判断 source 和数据流。

3. PoC 生成知识
   - 描述如何构造请求、命令、协议消息或利用载荷。
   - Exploit 阶段会用它生成可执行 PoC。

示例目录：

```text
skills/
  attack_surface/
    civetweb_audit/
      SKILL.md
      scripts/
        scan.py
  rpc_communication/
    SKILL.md
```

## EntrySpec / FunctionInfo 数据结构

Entry Discovery Agent 输出轻量 `EntrySpec`。structured output 顶层必须是 JSON object，避免 Codex/Responses API 拒绝顶层数组 schema：

```json
{
  "functions": [
    {
      "func_name": "add_user",
      "file_path": "src/web/user.c",
      "start_line": 120,
      "skill": "civetweb_audit"
    }
  ]
}
```

手工维护的 `--entry` JSON 或最终保存到 `discovered_functions.json` 的结果必须是轻量 `EntrySpec` 数组。Trace Agent 会把该入口描述交给 runtime，让 LLM 读取源码补齐 `end_line` 和 `code_snippet`，再转换为内部 `FunctionInfo`：

```json
[
  {
    "func_name": "add_user",
    "file_path": "src/web/user.c",
    "start_line": 120,
    "skill": "civetweb_audit"
  }
]
```

字段说明：

- `func_name`：入口函数名。
- `file_path`：入口函数所在文件。
- `start_line`：可选但强烈建议提供，用于区分同名函数或 C++ handler。
- `skill`：该入口函数应注入的攻击面 skill。

`FunctionInfo` 是内部完整结构，包含 `start_line`、`end_line`、`code_snippet` 和 `skill`。`EntrySpec` 和 `FunctionInfo` 都不再包含 `input` 字段；外部输入知识由攻击面 skill 提供。

## Audit Spec

漏洞类型 YAML 现在只需要定制两个字段：

```yaml
name: command_injection
user_prompt: |
  请审计当前入口函数是否存在命令注入问题。
  重点关注外部输入是否可达命令执行、脚本执行或系统调用。
```

不再需要配置 `agent_name`、`display_name`、system prompt、Exploit 开关等字段。这些内容会根据 `name` 自动生成。

约束：

- YAML 只能包含 `name` 和 `user_prompt`。
- `name` 会作为 `AuditResult.vulnerability_type`。
- `agent_name` 会由 `name` 自动生成，例如 `command_injection_audit`。

## AuditResult 数据结构

Audit 阶段每个漏洞类型一次对话，但一次对话可以返回多个 finding。工具会把每个 finding 转成一个 `AuditResult`：

```json
{
  "vulnerability_type": "command_injection",
  "finding_id": "command_injection_001",
  "title": "username reaches system command sink",
  "severity": "high",
  "is_vulnerable": true,
  "confidence": "high",
  "description": "外部输入 username 未经过安全过滤进入命令拼接。",
  "taint_flow": "HTTP parameter username -> add_user -> system",
  "recommendation": "避免字符串拼接命令，使用参数化 API 或严格白名单。",
  "code_map": []
}
```

`finding_id`、`title`、`severity` 用于区分同一漏洞类型下的多个独立问题。

## 输出目录

常见输出文件：

```text
output/
  audit_config.json
  audit_results.json
  audit_report.md
  audit_report.html
  audit_report.sarif
  audit_issues.sarif
  discovered_functions.json
  checkpoints/
```

说明：

- `audit_config.json`：本次审计配置快照。
- `audit_results.json`：完整结构化审计结果。
- `audit_report.md`：Markdown 审计报告。
- `audit_report.html`：HTML 审计报告。
- `audit_report.sarif`：SARIF 2.1.0 全量审计结果。
- `audit_issues.sarif`：仅包含漏洞 finding 的 SARIF 2.1.0 结果。
- `discovered_functions.json`：Entry Discovery 自动发现的入口函数列表。
- `checkpoints/`：断点续审数据。

## 目录结构

```text
cmd/
  tsj-audit/
  verify-go-refactor/

internal/
  checkpoint/
  config/
  export/
  models/
  pipeline/
  prompt/
  runtime/
  scanner/
  schema/
  skills/
  specs/
  status/

audit_specs/
  command_injection.yaml
  path_traversal.yaml
  brute_force.yaml
  password_reset.yaml
  loop.yaml

skills/
  attack_surface/
    civetweb_audit/
      SKILL.md
      scripts/scan.py
  rpc_communication/
    SKILL.md
```

## 开发验证

核心验证脚本：

```bash
GOCACHE="$PWD/.gocache" go run ./cmd/verify-go-refactor
```

从已有 `checkpoints/` 重新导出报告：

```bash
go run ./cmd/export-results --output-dir output
```
