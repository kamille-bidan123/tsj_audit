package scanner

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRunAttackSurfaceScanCivetWeb(t *testing.T) {
	project := t.TempDir()
	source := `#include "civetweb.h"
static int login_handler(struct mg_connection *conn, void *data) {
	return 1;
}
void register_routes(struct mg_context *ctx) {
	mg_set_request_handler(ctx, "/login", login_handler, 0);
}
`
	writeTestFile(t, project, "src/http.c", source)

	entries, ok, err := RunAttackSurfaceScan("civetweb_audit", project)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected native scanner")
	}
	if len(entries) != 1 {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].FuncName != "login_handler" || entries[0].FilePath != "src/http.c" {
		t.Fatalf("entry = %#v", entries[0])
	}
	if entries[0].Skill == nil || *entries[0].Skill != "civetweb_audit" {
		t.Fatalf("skill = %#v", entries[0].Skill)
	}
	if entries[0].StartLine == nil || *entries[0].StartLine != 2 {
		t.Fatalf("start_line = %#v", entries[0].StartLine)
	}
}

func TestRunAttackSurfaceScanIOCTL(t *testing.T) {
	project := t.TempDir()
	source := `#include <linux/fs.h>
static long device_ioctl(struct file *file, unsigned int cmd, unsigned long arg) {
	return 0;
}
static const struct file_operations fops = {
	.unlocked_ioctl = device_ioctl,
};
`
	writeTestFile(t, project, "drivers/dev.c", source)

	entries, ok, err := RunAttackSurfaceScan("ioctl_audit", project)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected native scanner")
	}
	if len(entries) != 1 {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].FuncName != "device_ioctl" || entries[0].FilePath != "drivers/dev.c" {
		t.Fatalf("entry = %#v", entries[0])
	}
	if entries[0].Skill == nil || *entries[0].Skill != "ioctl_audit" {
		t.Fatalf("skill = %#v", entries[0].Skill)
	}
}

func TestRunAttackSurfaceScanUnknownSkill(t *testing.T) {
	entries, ok, err := RunAttackSurfaceScan("unknown", t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if ok || entries != nil {
		t.Fatalf("entries=%#v ok=%t", entries, ok)
	}
}

func TestRunScanExecutesProvidedScanScriptEvenForBuiltInName(t *testing.T) {
	dir := t.TempDir()
	scanPath := filepath.Join(dir, "scripts", "scan.py")
	writeTestFile(t, dir, "scripts/scan.py", `
def scan_directory(project_path):
    return [{
        "func_name": "script_selected_entry",
        "file_path": "src/from_script.c",
        "skill": "script_skill",
        "start_line": 9,
    }]
`)

	entries, err := RunScan(context.Background(), scanPath, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].FuncName != "script_selected_entry" {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].Skill == nil || *entries[0].Skill != "script_skill" {
		t.Fatalf("skill = %#v", entries[0].Skill)
	}
}

func TestRunScanExecutesBinaryWithAbsoluteProjectPath(t *testing.T) {
	dir := t.TempDir()
	project := filepath.Join(dir, "project")
	if err := os.MkdirAll(project, 0755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, dir, "scan-bin", `#!/bin/sh
case "$1" in
  /*) ;;
  *) echo "project path is not absolute: $1" >&2; exit 7 ;;
esac
printf '[{"func_name":"binary_entry","file_path":"%s/src/main.c","start_line":5}]' "$1"
`)
	if err := os.Chmod(filepath.Join(dir, "scan-bin"), 0755); err != nil {
		t.Fatal(err)
	}

	cwd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := os.Chdir(cwd); err != nil {
			t.Fatal(err)
		}
	}()

	entries, err := RunScan(context.Background(), "scan-bin", "project")
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].FuncName != "binary_entry" {
		t.Fatalf("entries = %#v", entries)
	}
	if !filepath.IsAbs(entries[0].FilePath) || !strings.HasSuffix(entries[0].FilePath, filepath.Join("project", "src/main.c")) {
		t.Fatalf("file_path = %q, want absolute project path ending in project/src/main.c", entries[0].FilePath)
	}
}

func TestRunScanExecutesExecutablePythonFileDirectly(t *testing.T) {
	dir := t.TempDir()
	project := filepath.Join(dir, "project")
	if err := os.MkdirAll(project, 0755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, dir, "scan.py", `#!/bin/sh
printf '[{"func_name":"direct_executable","file_path":"src/direct.c","start_line":1}]'
`)
	if err := os.Chmod(filepath.Join(dir, "scan.py"), 0755); err != nil {
		t.Fatal(err)
	}

	entries, err := RunScan(context.Background(), filepath.Join(dir, "scan.py"), project)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].FuncName != "direct_executable" {
		t.Fatalf("entries = %#v", entries)
	}
}

func writeTestFile(t *testing.T, root string, rel string, content string) {
	t.Helper()
	path := filepath.Join(root, rel)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}
