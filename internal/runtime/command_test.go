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
	command := BuildClaudeCodeCommand("hello")

	want := []string{"claude", "-p", "--output-format", "json", "--permission-mode", "plan", "hello"}
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

func containsPair(values []string, key string, value string) bool {
	for i := 0; i+1 < len(values); i++ {
		if values[i] == key && values[i+1] == value {
			return true
		}
	}
	return false
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
