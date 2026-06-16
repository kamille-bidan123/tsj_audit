package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"tsj-audit/internal/extensions"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Go refactor verification passed")
}

func run() error {
	root, err := os.Getwd()
	if err != nil {
		return err
	}
	work := filepath.Join(os.TempDir(), "tsj-audit-go-verify")
	if err := os.RemoveAll(work); err != nil {
		return err
	}
	if err := os.MkdirAll(work, 0755); err != nil {
		return err
	}

	configPath := filepath.Join(work, "empty.env")
	entryPath := filepath.Join(work, "entries.json")
	outputDir := filepath.Join(work, "output")
	nativeProject := filepath.Join(work, "native-project")
	nativeOutputDir := filepath.Join(work, "native-output")
	scanOutputDir := filepath.Join(work, "scan-output")
	if err := os.WriteFile(configPath, []byte(""), 0644); err != nil {
		return err
	}
	entries := []map[string]any{{
		"func_name":  "verify_handler",
		"file_path":  "src/verify.c",
		"start_line": 9,
	}}
	entryData, err := json.Marshal(entries)
	if err != nil {
		return err
	}
	if err := os.WriteFile(entryPath, entryData, 0644); err != nil {
		return err
	}
	if err := writeNativeProject(nativeProject); err != nil {
		return err
	}
	for _, binary := range []string{"codex", "claude", "opencode"} {
		if _, err := exec.LookPath(binary); err != nil {
			return fmt.Errorf("required runtime CLI %q was not found in PATH", binary)
		}
	}
	if err := verifyExtensionManager(nativeProject); err != nil {
		return err
	}

	if err := runCommand(root, "go", "test", "./..."); err != nil {
		return err
	}
	if err := runCommand(root, "go", "build", "./cmd/tsj-audit"); err != nil {
		return err
	}
	_ = os.Remove(filepath.Join(root, "tsj-audit"))

	if err := runCommand(root,
		"go", "run", "./cmd/tsj-audit",
		"--config", configPath,
		"--agent-runtime", "mock",
		"--entry", entryPath,
		"--audit-types", "path_traversal",
		"--enable-fallback-audit",
		"--output-dir", outputDir,
	); err != nil {
		return err
	}
	scanOutput, err := runCommandOutput(root,
		"go", "run", "./cmd/scan",
		"--project-path", nativeProject,
		"--skill", "civetweb_audit",
	)
	if err != nil {
		return err
	}
	if !strings.Contains(scanOutput, "native_handler") {
		return fmt.Errorf("go scan command output missing native_handler")
	}
	if err := runCommand(root,
		"go", "run", "./cmd/export-results",
		"--output-dir", outputDir,
	); err != nil {
		return err
	}
	if err := runCommand(root,
		"go", "run", "./cmd/tsj-audit",
		"--config", configPath,
		"--agent-runtime", "mock",
		"--project-path", nativeProject,
		"--scan", "scripts/scan.py",
		"--audit-types", "path_traversal",
		"--disable-exploit",
		"--output-dir", scanOutputDir,
	); err != nil {
		return err
	}
	if err := runCommand(root,
		"go", "run", "./cmd/tsj-audit",
		"--config", configPath,
		"--agent-runtime", "mock",
		"--project-path", nativeProject,
		"--attack-surface-skill", "civetweb_audit",
		"--audit-types", "path_traversal",
		"--disable-exploit",
		"--output-dir", nativeOutputDir,
	); err != nil {
		return err
	}

	for _, runtime := range []string{"codex", "claudecode", "opencode"} {
		if err := runCommand(root,
			"go", "run", "./cmd/tsj-audit",
			"--config", configPath,
			"--agent-runtime", runtime,
			"--entry", entryPath,
			"--output-dir", filepath.Join(work, "dryrun-"+runtime),
			"--dry-run",
		); err != nil {
			return err
		}
	}

	expected := []string{
		filepath.Join(outputDir, "audit_config.json"),
		filepath.Join(outputDir, "audit_results.json"),
		filepath.Join(outputDir, "audit_report.md"),
		filepath.Join(outputDir, "audit_report.html"),
		filepath.Join(outputDir, "audit_report.sarif"),
		filepath.Join(outputDir, "audit_issues.sarif"),
		filepath.Join(outputDir, "checkpoints", "src_verify_c_9_verify_handler.json"),
	}
	for _, path := range expected {
		if _, err := os.Stat(path); err != nil {
			return fmt.Errorf("missing expected artifact %s: %w", path, err)
		}
	}

	report, err := os.ReadFile(filepath.Join(outputDir, "audit_report.md"))
	if err != nil {
		return err
	}
	for _, text := range []string{"verify_handler", "path_traversal", "fallback_security", "Vulnerable findings:"} {
		if !strings.Contains(string(report), text) {
			return fmt.Errorf("audit_report.md missing %q", text)
		}
	}
	sarif, err := os.ReadFile(filepath.Join(outputDir, "audit_report.sarif"))
	if err != nil {
		return err
	}
	for _, text := range []string{`"version": "2.1.0"`, `"ruleId": "path_traversal"`} {
		if !strings.Contains(string(sarif), text) {
			return fmt.Errorf("audit_report.sarif missing %q", text)
		}
	}
	discovered, err := os.ReadFile(filepath.Join(nativeOutputDir, "discovered_functions.json"))
	if err != nil {
		return err
	}
	for _, text := range []string{"native_handler", "civetweb_audit"} {
		if !strings.Contains(string(discovered), text) {
			return fmt.Errorf("native discovered_functions.json missing %q", text)
		}
	}
	scanReport, err := os.ReadFile(filepath.Join(scanOutputDir, "audit_report.md"))
	if err != nil {
		return err
	}
	if !strings.Contains(string(scanReport), "native_handler") {
		return fmt.Errorf("native --scan audit_report.md missing native_handler")
	}
	return nil
}

func verifyExtensionManager(project string) error {
	request := httptest.NewRequest(http.MethodGet, "/api/state", nil)
	response := httptest.NewRecorder()
	extensions.NewServer(project).Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		return fmt.Errorf("extension manager /api/state returned %d", response.Code)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		return err
	}
	if len(body["attack_surface_skills"].([]any)) == 0 {
		return fmt.Errorf("extension manager did not list attack surface skills")
	}
	return nil
}

func writeNativeProject(project string) error {
	skillDir := filepath.Join(project, "skills", "attack_surface", "civetweb_audit")
	sourceDir := filepath.Join(project, "src")
	if err := os.MkdirAll(skillDir, 0755); err != nil {
		return err
	}
	if err := os.MkdirAll(sourceDir, 0755); err != nil {
		return err
	}
	skill := `---
name: civetweb_audit
required_audit_types:
  - path_traversal
---
# CivetWeb Audit
`
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte(skill), 0644); err != nil {
		return err
	}
	source := `#include "civetweb.h"
static int native_handler(struct mg_connection *conn, void *data) {
	return 1;
}
void register_routes(struct mg_context *ctx) {
	mg_set_request_handler(ctx, "/native", native_handler, 0);
}
`
	return os.WriteFile(filepath.Join(sourceDir, "http.c"), []byte(source), 0644)
}

func runCommand(root string, name string, args ...string) error {
	_, err := runCommandOutput(root, name, args...)
	return err
}

func runCommandOutput(root string, name string, args ...string) (string, error) {
	command := exec.Command(name, args...)
	command.Dir = root
	command.Env = append(os.Environ(), "GOCACHE="+filepath.Join(root, ".gocache"))
	output, err := command.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("command failed: %s %s\n%s", name, strings.Join(args, " "), string(output))
	}
	return string(output), nil
}
