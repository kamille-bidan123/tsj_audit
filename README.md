# TSJ Audit

TSJ Audit 是一个多阶段 AI 代码审计工具。它从入口函数开始，执行入口发现、代码路径追踪、漏洞审计，并可选生成 Exploit/PoC 验证结果。

## 安装

从 GitHub Release 下载对应平台的二进制包。发布产物包含：

- `tsj-audit`：主审计命令。
- `civetweb_audit` / `ioctl_audit`：内置入口扫描器，可独立运行，也可作为 `--scan` 输入。
- `export-results`：从已有 checkpoint 重新导出报告。
- `manage-extensions`：本地扩展管理界面。
- `skill.zip`：内置 `skills/` 和 `audit_specs/`。

本地开发也可以直接运行：

```bash
go run ./cmd/tsj-audit --help
```

## 快速开始

推荐方式是用攻击面 skill 自动发现入口函数：

```bash
tsj-audit \
  --project-path /abs/path/to/project \
  --attack-surface-skill civetweb_audit \
  --output-dir output
```

审计 Linux ioctl 入口：

```bash
tsj-audit \
  --project-path /abs/path/to/linux-driver \
  --attack-surface-skill ioctl_audit \
  --output-dir output
```

使用扫描器作为入口：

```bash
tsj-audit \
  --project-path /abs/path/to/project \
  --scan ./civetweb_audit \
  --output-dir output
```

`--scan` 如果指向可执行文件，会直接以如下形式运行：

```text
<scan_binary> <absolute_project_path>
```

如果 `--scan` 指向非可执行 `.py` 文件，则走 Python 扫描脚本兼容路径。

使用手工入口 JSON：

```bash
tsj-audit \
  --project-path /abs/path/to/project \
  --entry entries.json \
  --output-dir output
```

`--scan`、`--entry`、`--attack-surface-skill` 三者互斥，一次审计只能选择一种入口来源。

## 入口格式

`--entry` 接收 `EntrySpec[]` JSON：

```json
[
  {
    "func_name": "device_ioctl",
    "file_path": "drivers/device.c",
    "start_line": 120,
    "skill": "ioctl_audit"
  }
]
```

字段说明：

- `func_name`：入口函数名。
- `file_path`：相对 `project_path` 的源码路径。
- `start_line`：可选，建议填写，用于区分同名函数。
- `skill`：可选，指定该入口审计时注入的 skill。

## 审计流程

1. Entry Discovery：使用 `--attack-surface-skill` 时启用，由 runtime 根据 skill 自动发现入口函数。
2. Trace：补齐入口函数上下文，生成代码逻辑说明和 `code_map`。
3. Audit：按漏洞类型逐类审计；漏洞类型来自 `audit_specs/*.yaml`。
4. Exploit：默认开启，对中高置信度 finding 生成 PoC；可用 `--disable-exploit` 关闭。

开启兜底审计：

```bash
tsj-audit \
  --project-path /abs/path/to/project \
  --attack-surface-skill civetweb_audit \
  --enable-fallback-audit
```

断点续审：

```bash
tsj-audit --resume --output-dir output --entry entries.json
```

已跳过但没有写入 checkpoint 的函数，在下一次 `--resume` 时会重新尝试。

## 配置

配置优先级从高到低：

1. 命令行参数
2. `--config` 指定的 `.env` 风格配置文件
3. 当前目录或用户主目录下的 `.env`
4. 代码默认值

常用配置：

```env
agent_runtime = "codex"          # codex / claudecode / opencode
project_path = "."
output_dir = "output"

attack_surface_skill = ""
scan = ""
entry = ""
audit_types = []

external_runtime_timeout_seconds = 1800
external_runtime_request_retries = 2
opencode_request_retries = 2
function_concurrency = 1

disable_exploit = false
enable_fallback_audit = false
resume = false
debug = false

target_base_url = "http://localhost:8081"
```

Runtime 说明：

- `codex`：命令型 runtime，使用 JSON schema 输出。
- `claudecode`：命令型 runtime，调用 `claude -p --output-format json --json-schema ...`。
- `opencode`：HTTP runtime，默认地址 `http://127.0.0.1:4096`。

重试说明：

- `external_runtime_request_retries` 控制命令型 runtime 重试次数，默认 2。
- `claudecode` 只要执行 Claude 或解析 Claude 输出时报错，都会按该次数重试。
- `opencode_request_retries` 控制 OpenCode HTTP 请求超时后的重试次数，默认 2。

## Skill 和 Audit Spec

攻击面 skill 位于：

```text
skills/attack_surface/<skill_name>/SKILL.md
```

内置攻击面：

- `civetweb_audit`
- `ioctl_audit`

skill frontmatter 可以绑定必审漏洞类型：

```yaml
---
name: ioctl_audit
description: Linux ioctl attack surface
required_audit_types:
  - ioctl_user_kernel_boundary
  - ioctl_user_buffer_overflow
---
```

漏洞审计规则位于 `audit_specs/*.yaml`。当前内置类型包括：

- `brute_force`
- `command_injection`
- `ioctl_user_buffer_overflow`
- `ioctl_user_kernel_boundary`
- `loop`
- `password_reset`
- `path_traversal`

YAML 格式：

```yaml
name: command_injection
user_prompt: |
  请审计当前入口函数是否存在命令注入问题。
```

## 输出

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
    logs/
    conversations/
```

说明：

- `audit_results.json`：完整结构化结果。
- `audit_report.md` / `audit_report.html`：可读报告。
- `audit_report.sarif`：全量 SARIF 结果。
- `audit_issues.sarif`：仅包含漏洞 finding 的 SARIF 结果。
- `discovered_functions.json`：自动发现的入口函数。
- `checkpoints/`：断点续审数据、函数日志和 runtime conversation 记录。

## 辅助命令

只运行内置入口扫描器：

```bash
civetweb_audit /abs/path/to/project
ioctl_audit /abs/path/to/project
```

开发环境也可以运行通用扫描命令：

```bash
go run ./cmd/scan --project-path /abs/path/to/project --skill civetweb_audit
go run ./cmd/scan --project-path /abs/path/to/project --skill ioctl_audit
```

重新导出报告：

```bash
export-results --output-dir output
```

继承 SARIF Explorer 人工审核状态：

```bash
export-results --output-dir output --inherit-sarif old_reviewed.sarif
```

启动本地扩展管理界面：

```bash
manage-extensions --host 127.0.0.1 --port 8765
```

## 开发验证

```bash
GOCACHE="$PWD/.gocache" go test ./...
GOCACHE="$PWD/.gocache" go run ./cmd/verify-go-refactor
```
