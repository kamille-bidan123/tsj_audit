package main

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
	"time"

	"tsj-audit/internal/config"
	"tsj-audit/internal/runtime"
)

func TestRunPrintsBanner(t *testing.T) {
	var stderr bytes.Buffer

	if err := run(&stderr, nil); err != nil {
		t.Fatal(err)
	}

	got := stderr.String()
	want := "tsj-audit Go refactor\nruntime=codex output=output\n"
	if got != want {
		t.Fatalf("stderr = %q, want %q", got, want)
	}
}

func TestRunLoadsCLIConfig(t *testing.T) {
	var stderr bytes.Buffer

	if err := run(&stderr, []string{"--agent-runtime", "opencode", "--output-dir", "custom-output"}); err != nil {
		t.Fatal(err)
	}

	got := stderr.String()
	want := "tsj-audit Go refactor\nruntime=opencode output=custom-output\n"
	if got != want {
		t.Fatalf("stderr = %q, want %q", got, want)
	}
}

func TestRunWithMockRuntimeWritesCheckpoint(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	outputDir := filepath.Join(dir, "output")
	entryJSON := `[{"func_name":"handle_cli","file_path":"src/http.c","start_line":3}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	var stderr bytes.Buffer
	err := run(&stderr, []string{
		"--agent-runtime", "mock",
		"--entry", entryPath,
		"--output-dir", outputDir,
	})
	if err != nil {
		t.Fatal(err)
	}

	checkpointPath := filepath.Join(outputDir, "checkpoints", "src_http_c_3_handle_cli.json")
	if _, err := os.Stat(checkpointPath); err != nil {
		t.Fatalf("expected checkpoint at %s: %v", checkpointPath, err)
	}
	configPath := filepath.Join(outputDir, "audit_config.json")
	if _, err := os.Stat(configPath); err != nil {
		t.Fatalf("expected config at %s: %v", configPath, err)
	}
	for _, name := range []string{"audit_results.json", "audit_report.md", "audit_report.html", "audit_report.sarif", "audit_issues.sarif"} {
		path := filepath.Join(outputDir, name)
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("expected report at %s: %v", path, err)
		}
	}
}

func TestCreateRuntimeRejectsUnimplementedRuntime(t *testing.T) {
	if _, err := createRuntime(config.Config{AgentRuntime: "unknown"}); err == nil {
		t.Fatal("expected unimplemented runtime error")
	}
}

func TestCreateRuntimeConfiguresCommandClient(t *testing.T) {
	client, err := createRuntime(config.Config{
		AgentRuntime:                  "codex",
		ProjectPath:                   "/tmp/project",
		ExternalRuntimeTimeoutSeconds: 42,
	})
	if err != nil {
		t.Fatal(err)
	}
	command, ok := client.(runtime.Command)
	if !ok {
		t.Fatalf("client = %#v", client)
	}
	if command.ProjectDir != "/tmp/project" {
		t.Fatalf("ProjectDir = %q", command.ProjectDir)
	}
	if command.Timeout != 42*time.Second {
		t.Fatalf("Timeout = %s", command.Timeout)
	}
}

func TestRunRejectsExistingCheckpointsWithoutResume(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	outputDir := filepath.Join(dir, "output")
	checkpointDir := filepath.Join(outputDir, "checkpoints")
	if err := os.MkdirAll(checkpointDir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(checkpointDir, "old.json"), []byte(`{}`), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(entryPath, []byte(`[{"func_name":"handle","file_path":"src/http.c"}]`), 0644); err != nil {
		t.Fatal(err)
	}

	var stderr bytes.Buffer
	err := run(&stderr, []string{
		"--agent-runtime", "mock",
		"--entry", entryPath,
		"--output-dir", outputDir,
	})
	if err == nil {
		t.Fatal("expected existing checkpoint error")
	}
}

func TestRunHelpPrintsUsage(t *testing.T) {
	var stderr bytes.Buffer
	err := run(&stderr, []string{"--help"})
	if err != nil {
		t.Fatal(err)
	}
	if got := stderr.String(); !bytes.Contains([]byte(got), []byte("Usage of tsj-audit")) {
		t.Fatalf("help output missing usage: %q", got)
	}
}

func TestRunDryRunDoesNotWriteOutput(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	outputDir := filepath.Join(dir, "output")
	if err := os.WriteFile(entryPath, []byte(`[{"func_name":"handle","file_path":"src/http.c"}]`), 0644); err != nil {
		t.Fatal(err)
	}

	var stderr bytes.Buffer
	err := run(&stderr, []string{
		"--agent-runtime", "codex",
		"--entry", entryPath,
		"--output-dir", outputDir,
		"--dry-run",
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(outputDir); !os.IsNotExist(err) {
		t.Fatalf("dry-run should not create output dir, stat err=%v", err)
	}
}

func TestRunDryRunDoesNotWriteOpenCodeConfig(t *testing.T) {
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(cwd); err != nil {
			t.Fatalf("restore cwd: %v", err)
		}
	})
	configPath := filepath.Join(dir, "empty.env")
	entryPath := filepath.Join(dir, "entries.json")
	if err := os.WriteFile(configPath, nil, 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(entryPath, []byte(`[{"func_name":"handle","file_path":"src/http.c"}]`), 0644); err != nil {
		t.Fatal(err)
	}

	var stderr bytes.Buffer
	err = run(&stderr, []string{
		"--config", configPath,
		"--agent-runtime", "opencode",
		"--entry", entryPath,
		"--project-path", dir,
		"--dry-run",
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "opencode.json")); !os.IsNotExist(err) {
		t.Fatalf("dry-run should not create opencode.json, stat err=%v", err)
	}
}

func TestLoadConfigParsesOpenCodeEventStreamFlag(t *testing.T) {
	cfg, err := loadConfig([]string{
		"--agent-runtime", "opencode",
		"--opencode-enable-event-stream",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !cfg.OpenCodeEnableEventStream {
		t.Fatal("expected opencode event stream flag to be enabled")
	}
}
