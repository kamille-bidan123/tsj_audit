package opencodeconfig

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestEnsureWritesOfficialPermissionConfig(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(projectDir, "opencode.json")

	writtenPath, err := Ensure("opencode.json", projectDir)
	if err != nil {
		t.Fatal(err)
	}
	if writtenPath != configPath {
		t.Fatalf("path = %q, want %q", writtenPath, configPath)
	}

	config := readConfig(t, configPath)
	permission := config["permission"].(map[string]any)
	bash := permission["bash"].(map[string]any)
	if bash["rg *"] != "allow" || bash["*"] != "ask" {
		t.Fatalf("bash permission = %#v", bash)
	}
	external := permission["external_directory"].(map[string]any)
	if external[projectDir] != "allow" || external[filepath.Join(projectDir, "**")] != "allow" || external["*"] != "ask" {
		t.Fatalf("external_directory permission = %#v", external)
	}
	if permission["edit"] != "deny" {
		t.Fatalf("edit permission = %#v", permission["edit"])
	}
}

func TestEnsureDefaultsConfigPathToProjectDirectory(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatal(err)
	}

	writtenPath, err := Ensure("", projectDir)
	if err != nil {
		t.Fatal(err)
	}

	want := filepath.Join(projectDir, "opencode.json")
	if writtenPath != want {
		t.Fatalf("path = %q, want %q", writtenPath, want)
	}
	if _, err := os.Stat(want); err != nil {
		t.Fatal(err)
	}
}

func TestEnsureResolvesRelativeConfigPathInsideProjectDirectory(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatal(err)
	}

	writtenPath, err := Ensure(".opencode/runtime.json", projectDir)
	if err != nil {
		t.Fatal(err)
	}

	want := filepath.Join(projectDir, ".opencode", "runtime.json")
	if writtenPath != want {
		t.Fatalf("path = %q, want %q", writtenPath, want)
	}
	if _, err := os.Stat(want); err != nil {
		t.Fatal(err)
	}
}

func TestEnsureMergesExistingConfig(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(dir, "opencode.json")
	existing := `{"theme":"dark","permission":{"bash":{"git *":"allow"},"edit":"ask"}}`
	if err := os.WriteFile(configPath, []byte(existing), 0644); err != nil {
		t.Fatal(err)
	}

	if _, err := Ensure(configPath, projectDir); err != nil {
		t.Fatal(err)
	}

	config := readConfig(t, configPath)
	if config["theme"] != "dark" {
		t.Fatalf("config = %#v", config)
	}
	permission := config["permission"].(map[string]any)
	bash := permission["bash"].(map[string]any)
	if bash["git *"] != "allow" || bash["rg *"] != "allow" {
		t.Fatalf("bash permission = %#v", bash)
	}
	if permission["edit"] != "ask" {
		t.Fatalf("existing edit permission should be preserved: %#v", permission["edit"])
	}
}

func readConfig(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(data, &config); err != nil {
		t.Fatal(err)
	}
	return config
}
