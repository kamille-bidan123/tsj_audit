package runtime

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"tsj-audit/internal/status"
)

func TestBuildCodexCommandUsesReadOnlySandboxByDefault(t *testing.T) {
	command := BuildCodexCommand("Trace", "/tmp/schema.json", "/tmp/output.json")

	if command[0] != "codex" || command[1] != "exec" {
		t.Fatalf("command = %#v", command)
	}
	if !containsPair(command, "--sandbox", "read-only") {
		t.Fatalf("command missing read-only sandbox: %#v", command)
	}
	if !containsPair(command, "--output-schema", "/tmp/schema.json") {
		t.Fatalf("command missing schema: %#v", command)
	}
}

func TestBuildCodexCommandUsesWorkspaceWriteForExploit(t *testing.T) {
	command := BuildCodexCommand("Exploit", "/tmp/schema.json", "/tmp/output.json")

	if !containsPair(command, "--sandbox", "workspace-write") {
		t.Fatalf("command missing workspace-write sandbox: %#v", command)
	}
}

func TestBuildClaudeCodeCommand(t *testing.T) {
	schema := `{"type":"object","properties":{"ok":{"type":"boolean"}}}`
	command := BuildClaudeCodeCommand("hello", schema)

	want := []string{"claude", "-p", "--output-format", "json", "--json-schema", schema, "--permission-mode", "plan", "hello"}
	if !equalStrings(command, want) {
		t.Fatalf("command = %#v, want %#v", command, want)
	}
}

func TestUnwrapClaudeCodeOutput(t *testing.T) {
	raw := []byte(`{"type":"result","is_error":false,"result":"Here is JSON:\n{\"ok\":true}"}`)

	unwrapped, err := unwrapClaudeCodeOutput(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(unwrapped) != `{"ok":true}` {
		t.Fatalf("unwrapped = %s", unwrapped)
	}
}

func TestUnwrapClaudeCodeError(t *testing.T) {
	raw := []byte(`{"type":"result","is_error":true,"result":"API Error: Unable to connect"}`)

	_, err := unwrapClaudeCodeOutput(raw)
	if err == nil {
		t.Fatal("expected error")
	}
	if !containsAll(err.Error(), "claudecode", "API Error") {
		t.Fatalf("error = %v", err)
	}
}

func TestUnwrapClaudeCodeErrorWithoutResult(t *testing.T) {
	raw := []byte(`{"type":"result","subtype":"error_during_execution","is_error":true,"errors":["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"]}`)

	_, err := unwrapClaudeCodeOutput(raw)
	if err == nil {
		t.Fatal("expected error")
	}
	if !containsAll(err.Error(), "claudecode", "ede_diagnostic") {
		t.Fatalf("error = %v", err)
	}
}

func TestUnwrapClaudeCodeStructuredResultObject(t *testing.T) {
	raw := []byte(`{"type":"result","is_error":false,"result":{"ok":true}}`)

	unwrapped, err := unwrapClaudeCodeOutput(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(unwrapped) != `{"ok":true}` {
		t.Fatalf("unwrapped = %s", unwrapped)
	}
}

func TestUnwrapClaudeCodeStructuredOutput(t *testing.T) {
	raw := []byte(`{"type":"result","subtype":"success","is_error":false,"result":"Done.","structured_output":{"ok":true,"message":"hello"}}`)

	unwrapped, err := unwrapClaudeCodeOutput(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(unwrapped) != `{"ok":true,"message":"hello"}` {
		t.Fatalf("unwrapped = %s", unwrapped)
	}
}

func TestCommandErrorDetailIncludesStdout(t *testing.T) {
	detail := commandErrorDetail([]byte("stdout failure"), nil)
	if !containsAll(detail, "stdout", "stdout failure") {
		t.Fatalf("detail = %q", detail)
	}
}

func TestCommandRuntimeLogsClaudeCodeStartAndCompletion(t *testing.T) {
	dir := t.TempDir()
	claudePath := filepath.Join(dir, "claude")
	script := "#!/bin/sh\nprintf '%s\\n' '{\"type\":\"result\",\"is_error\":false,\"result\":\"{\\\"ok\\\":true}\"}'\n"
	if err := os.WriteFile(claudePath, []byte(script), 0755); err != nil {
		t.Fatal(err)
	}
	oldPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath)

	state := status.New()
	var entries []status.FunctionLogEntry
	state.SetTaskStage("Trace", "entry-key", "handle", "-")
	state.SetFunctionLogWriter(func(entry status.FunctionLogEntry) {
		entries = append(entries, entry)
	})

	raw, messages, err := Command{Name: "claudecode"}.RunJSON(context.Background(), RunJSONRequest{
		StageName:    "Trace",
		EntryKey:     "entry-key",
		FunctionName: "handle",
		UserPrompt:   "return json",
		Status:       state,
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"ok":true}` {
		t.Fatalf("raw = %s", raw)
	}
	if len(messages) == 0 {
		t.Fatalf("messages = %#v", messages)
	}
	if len(messages) != 2 || messages[1].Role != "assistant_raw" || !strings.Contains(messages[1].Content, `"type":"result"`) {
		t.Fatalf("messages should include raw claude wrapper = %#v", messages)
	}
	var sawStart, sawComplete bool
	for _, entry := range entries {
		if strings.Contains(entry.Message, "[claudecode] starting command") {
			sawStart = true
		}
		if strings.Contains(entry.Message, "[claudecode] completed command") {
			sawComplete = true
		}
	}
	if !sawStart || !sawComplete {
		data, _ := json.Marshal(entries)
		t.Fatalf("missing claudecode runtime logs: %s", data)
	}
}

func TestCommandRuntimeRetriesClaudeCodeMissingJSONObject(t *testing.T) {
	dir := t.TempDir()
	claudePath := filepath.Join(dir, "claude")
	countPath := filepath.Join(dir, "count")
	script := `#!/bin/sh
count_file="` + countPath + `"
count=0
if [ -f "$count_file" ]; then
  count="$(cat "$count_file")"
fi
count=$((count + 1))
printf '%s' "$count" > "$count_file"
if [ "$count" -eq 1 ]; then
  printf '%s\n' '{"type":"result","is_error":false,"result":"I cannot provide that as JSON yet."}'
  exit 0
fi
printf '%s\n' '{"type":"result","is_error":false,"result":"{\"ok\":true}"}'
`
	if err := os.WriteFile(claudePath, []byte(script), 0755); err != nil {
		t.Fatal(err)
	}
	oldPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath)

	raw, _, err := Command{Name: "claudecode", RequestRetries: 1}.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "return json",
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"ok":true}` {
		t.Fatalf("raw = %s", raw)
	}
	countData, err := os.ReadFile(countPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(countData) != "2" {
		t.Fatalf("claude calls = %s", countData)
	}
}

func TestCommandRuntimePassesJSONSchemaToClaudeCode(t *testing.T) {
	dir := t.TempDir()
	claudePath := filepath.Join(dir, "claude")
	argsPath := filepath.Join(dir, "args.json")
	script := `#!/bin/sh
python3 - "$@" <<'PY'
import json
import sys
from pathlib import Path
Path("` + argsPath + `").write_text(json.dumps(sys.argv[1:]))
PY
printf '%s\n' '{"type":"result","is_error":false,"result":"{\"ok\":true}"}'
`
	if err := os.WriteFile(claudePath, []byte(script), 0755); err != nil {
		t.Fatal(err)
	}
	oldPath := os.Getenv("PATH")
	t.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath)

	schema := json.RawMessage(`{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}`)
	raw, _, err := Command{Name: "claudecode"}.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "return json",
		Schema:     schema,
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"ok":true}` {
		t.Fatalf("raw = %s", raw)
	}
	argsData, err := os.ReadFile(argsPath)
	if err != nil {
		t.Fatal(err)
	}
	var args []string
	if err := json.Unmarshal(argsData, &args); err != nil {
		t.Fatal(err)
	}
	index := indexOf(args, "--json-schema")
	if index < 0 || index+1 >= len(args) {
		t.Fatalf("args missing --json-schema: %#v", args)
	}
	if !json.Valid([]byte(args[index+1])) {
		t.Fatalf("schema argument is not valid JSON: %q", args[index+1])
	}
	if args[index+1] != string(schema) {
		t.Fatalf("schema argument = %s, want %s", args[index+1], schema)
	}
}

func containsPair(values []string, key string, value string) bool {
	for i := 0; i+1 < len(values); i++ {
		if values[i] == key && values[i+1] == value {
			return true
		}
	}
	return false
}

func indexOf(values []string, needle string) int {
	for index, value := range values {
		if value == needle {
			return index
		}
	}
	return -1
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
