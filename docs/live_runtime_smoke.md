# Live Runtime Smoke Results

Date: 2026-06-01

## Verified

- `codex` live smoke completed successfully with:
  - `go run ./cmd/tsj-audit`
  - `--agent-runtime codex`
  - `--entry /private/tmp/tsj-audit-live-smoke/entries.json`
  - `--audit-types path_traversal`
  - `--disable-exploit`
- Codex generated all expected artifacts:
  - `audit_config.json`
  - `audit_results.json`
  - `audit_report.md`
  - `audit_report.html`
  - `audit_report.sarif`
  - `audit_issues.sarif`
  - checkpoint 文件；当前版本按 `file_path:start_line:func_name` 生成可读 key，并将文件名中的路径分隔符替换为 `_`

## Blocked By External Runtime Environment

- `claudecode` live smoke reached the Claude Code CLI, but the CLI returned:
  - `API Error: Unable to connect to API (ECONNREFUSED)`
- `opencode` live smoke reached the local server after `opencode serve` was started:
  - session creation succeeded
  - structured-output probe executed and fell back to prompt mode because the probe returned `ok=false`
  - status server exposed an OpenCode permission request
  - one-time permission approval through `/api/permission` succeeded
  - the run then remained in the Trace stage without producing a checkpoint or report artifact and was stopped manually after several minutes

## Local Verification Still Passing

The Go refactor is locally verified by:

```bash
GOCACHE="$PWD/.gocache" go test ./...
GOCACHE="$PWD/.gocache" go run ./cmd/verify-go-refactor
GOCACHE="$PWD/.gocache" go build ./cmd/tsj-audit ./cmd/manage-extensions ./cmd/export-results ./cmd/scan
```

`cmd/verify-go-refactor` verifies local Go behavior without calling external models. Live OpenCode currently requires model/provider configuration that returns a final JSON response in prompt fallback mode.
