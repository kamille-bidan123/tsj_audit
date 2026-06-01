package runtime

import (
	"strings"
	"testing"
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

	want := []string{"claude", "-p", "--output-format", "json", "hello"}
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
