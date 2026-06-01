package scanner

import (
	"context"
	"os"
	"path/filepath"
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

func TestRunScanUsesNativeScannerForBuiltInScanScript(t *testing.T) {
	project := t.TempDir()
	writeTestFile(t, project, "src/http.c", `#include "civetweb.h"
static int scan_handler(struct mg_connection *conn, void *data) {
	return 1;
}
void register_routes(struct mg_context *ctx) {
	mg_set_request_handler(ctx, "/scan", scan_handler, 0);
}
`)

	entries, err := RunScan(context.Background(), "scripts/scan.py", project)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].FuncName != "scan_handler" {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].Skill == nil || *entries[0].Skill != "civetweb_audit" {
		t.Fatalf("skill = %#v", entries[0].Skill)
	}
}

func TestNativeSkillForScanPath(t *testing.T) {
	cases := map[string]string{
		"scripts/scan.py":       "civetweb_audit",
		"scripts/scan_ioctl.py": "ioctl_audit",
		"skills/attack_surface/ioctl_audit/scripts/scan.py":    "ioctl_audit",
		"skills/attack_surface/civetweb_audit/scripts/scan.py": "civetweb_audit",
	}
	for path, want := range cases {
		got, ok := nativeSkillForScanPath(path)
		if !ok || got != want {
			t.Fatalf("nativeSkillForScanPath(%q) = %q, %t; want %q, true", path, got, ok, want)
		}
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
