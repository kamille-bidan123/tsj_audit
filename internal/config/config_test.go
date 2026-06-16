package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadDefaultsWithoutEnvFile(t *testing.T) {
	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	tempDir := t.TempDir()
	if err := os.Chdir(tempDir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chdir(cwd); err != nil {
			t.Fatalf("restore cwd: %v", err)
		}
	})

	cfg, err := Load(Args{})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.AgentRuntime != "codex" {
		t.Fatalf("AgentRuntime = %q", cfg.AgentRuntime)
	}
	if cfg.OutputDir != "output" {
		t.Fatalf("OutputDir = %q", cfg.OutputDir)
	}
}

func TestExplicitConfigFileAndCLIOverride(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "opencode.env")
	content := "agent_runtime = \"opencode\" # opencode / codex / claudecode\noutput_dir = \"from-env\" # output path\n"
	if err := os.WriteFile(configFile, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(Args{
		ConfigFile: configFile,
		OutputDir:  "from-cli",
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.AgentRuntime != "opencode" {
		t.Fatalf("AgentRuntime = %q", cfg.AgentRuntime)
	}
	if cfg.OutputDir != "from-cli" {
		t.Fatalf("OutputDir = %q", cfg.OutputDir)
	}
}

func TestEnvParserPreservesHashInsideQuotes(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "quoted.env")
	content := "output_dir = \"out#1\" # inline comment\n"
	if err := os.WriteFile(configFile, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(Args{ConfigFile: configFile})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.OutputDir != "out#1" {
		t.Fatalf("OutputDir = %q", cfg.OutputDir)
	}
}

func TestAuditTypesParsing(t *testing.T) {
	cfg, err := Load(Args{AuditTypes: "path_traversal, command_injection"})
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.AuditTypes) != 2 {
		t.Fatalf("AuditTypes = %#v", cfg.AuditTypes)
	}
	if cfg.AuditTypes[0] != "path_traversal" || cfg.AuditTypes[1] != "command_injection" {
		t.Fatalf("AuditTypes = %#v", cfg.AuditTypes)
	}
}

func TestFunctionConcurrencyFromEnvAndCLI(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "concurrency.env")
	if err := os.WriteFile(configFile, []byte("function_concurrency = 2\n"), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(Args{ConfigFile: configFile})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.FunctionConcurrency != 2 {
		t.Fatalf("FunctionConcurrency = %d", cfg.FunctionConcurrency)
	}

	cfg, err = Load(Args{ConfigFile: configFile, FunctionConcurrency: 4})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.FunctionConcurrency != 4 {
		t.Fatalf("CLI FunctionConcurrency = %d", cfg.FunctionConcurrency)
	}
}

func TestFunctionConcurrencyDefaultsToOne(t *testing.T) {
	cfg := defaults()
	if cfg.FunctionConcurrency != 1 {
		t.Fatalf("FunctionConcurrency = %d", cfg.FunctionConcurrency)
	}
}

func TestBooleanEnvAndCLIOverrides(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "opencode.env")
	content := "opencode_enable_event_stream = true\ndry_run = true\n"
	if err := os.WriteFile(configFile, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	disableEventStream := false
	cfg, err := Load(Args{
		ConfigFile:                configFile,
		OpenCodeEnableEventStream: &disableEventStream,
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.OpenCodeEnableEventStream {
		t.Fatal("CLI boolean override should disable opencode event stream")
	}
	if !cfg.DryRun {
		t.Fatal("dry_run env value should be parsed")
	}
}

func TestOpenCodeProjectConfigOptionsFromEnv(t *testing.T) {
	dir := t.TempDir()
	configFile := filepath.Join(dir, "opencode.env")
	content := "opencode_inject_project_config = false\nopencode_config_path = \"custom-opencode.json\"\nopencode_request_retries = 4\n"
	if err := os.WriteFile(configFile, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(Args{ConfigFile: configFile})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.OpenCodeInjectProjectConfig {
		t.Fatal("expected opencode project config injection to be disabled")
	}
	if cfg.OpenCodeConfigPath != "custom-opencode.json" {
		t.Fatalf("OpenCodeConfigPath = %q", cfg.OpenCodeConfigPath)
	}
	if cfg.OpenCodeRequestRetries != 4 {
		t.Fatalf("OpenCodeRequestRetries = %d", cfg.OpenCodeRequestRetries)
	}
}

func TestRejectMissingExplicitConfigFile(t *testing.T) {
	_, err := Load(Args{ConfigFile: filepath.Join(t.TempDir(), "missing.env")})
	if err == nil {
		t.Fatal("expected missing explicit config file error")
	}
}
