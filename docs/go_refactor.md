# Go Refactor Status

This branch contains the Go-first TSJ Audit refactor.

## Current Capabilities

- Go CLI entry point: `cmd/tsj-audit`
- Go native scan command: `cmd/scan`
- Config loading from defaults, `.env`, explicit `--config`, and CLI overrides
- Core JSON models compatible with the Python artifacts
- Entry loading from `--entry`
- `--scan` support with native Go handling for built-in `scripts/scan.py` and `scripts/scan_ioctl.py`, plus Python compatibility fallback for custom scripts
- Native Go attack-surface scanning for built-in `civetweb_audit` and `ioctl_audit`
- Attack surface skill discovery through native Go scanners, custom `skills/attack_surface/<name>/scripts/scan.py` compatibility, or runtime-backed discovery
- Runtime-backed attack surface entry discovery fallback when a skill does not provide `scripts/scan.py`
- Skill frontmatter parsing for `required_audit_types`
- Audit spec loading from `audit_specs/*.yaml`
- Runtime interface with:
  - `mock`
  - `opencode`
  - `codex`
  - `claudecode`
- Pipeline stages:
  - Trace
  - Audit
  - Exploit
- Unified runtime prompts with stage schema injection
- Go-generated JSON schemas for entry discovery, trace, audit, and exploit outputs
- AuditOutput-compatible parsing:
  - top-level single-result output
  - `findings` multi-result output
- `--enable-fallback-audit` support through `fallback_security`
- Checkpoint save/load and `--resume` skip behavior
- Output overwrite protection when checkpoints already exist
- Local status service startup from the CLI. If the host environment forbids listening sockets, the CLI logs a warning and continues the audit.
- Status API supports permission request snapshots and `/api/permission` replies.
- Go extension manager command: `cmd/manage-extensions`
- Go standalone report exporter command: `cmd/export-results`
- OpenCode permission support includes `/event` permission-event parsing, `/permission/{id}/reply`, single-pass `/permission` polling primitives, and background permission polling during each `RunJSON` session.
- `--dry-run` support to validate config and runtime construction without calling model runtimes.
- Report export:
  - `audit_results.json`
  - `audit_report.md`
  - `audit_report.html`
  - `audit_report.sarif`
  - `audit_issues.sarif`
- Reports include vulnerable-finding counts, severity counts, taint flow, recommendation, code map references, exploit results, and SARIF 2.1.0 output.

## Smoke Test

Use an explicit empty config file when running from the repository root if local `.env` contains an entry source.

```bash
mkdir -p /private/tmp/tsj-audit-go-smoke
printf '' > /private/tmp/tsj-audit-go-smoke/empty.env
printf '[{"func_name":"smoke_handler","file_path":"src/smoke.c","start_line":5}]' \
  > /private/tmp/tsj-audit-go-smoke/entries.json

GOCACHE="$PWD/.gocache" go run ./cmd/tsj-audit \
  --config /private/tmp/tsj-audit-go-smoke/empty.env \
  --agent-runtime mock \
  --entry /private/tmp/tsj-audit-go-smoke/entries.json \
  --audit-types path_traversal \
  --enable-fallback-audit \
  --output-dir /private/tmp/tsj-audit-go-smoke/output
```

Runtime construction dry-run:

```bash
GOCACHE="$PWD/.gocache" go run ./cmd/tsj-audit \
  --config /private/tmp/tsj-audit-go-smoke/empty.env \
  --agent-runtime codex \
  --entry /private/tmp/tsj-audit-go-smoke/entries.json \
  --output-dir /private/tmp/tsj-audit-go-smoke/dryrun \
  --dry-run
```

Expected files:

```text
audit_config.json
audit_results.json
audit_report.html
audit_report.md
audit_report.sarif
audit_issues.sarif
checkpoints/src_smoke_c_5_smoke_handler.json
```

## Verification

```bash
GOCACHE="$PWD/.gocache" go test ./...
GOCACHE="$PWD/.gocache" go run ./cmd/verify-go-refactor
```

## Verification Boundaries

- Local verification covers Go tests, mock end-to-end audit execution, native Go attack-surface scanning, report artifact generation, SARIF generation, and runtime construction dry-runs for `codex`, `claudecode`, and `opencode`.
- `cmd/verify-go-refactor` verifies that `codex`, `claude`, and `opencode` CLIs are present. Dry-run verification does not call external models.
- Live model smoke status is recorded in `docs/live_runtime_smoke.md`. `codex` live smoke passed; `claudecode` is blocked by Claude API connection refusal; `opencode` reaches the local serve instance and permission flow, but the configured model did not return a final Trace JSON response during smoke testing.
- The primary CLI, pipeline, runtime clients, status service, extension manager, standalone scanner/exporter, and verifier are Go. Python is retained only for optional custom scan-script compatibility.
