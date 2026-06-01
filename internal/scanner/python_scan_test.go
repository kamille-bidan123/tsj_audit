package scanner

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRunPythonScan(t *testing.T) {
	dir := t.TempDir()
	scanPath := filepath.Join(dir, "scan.py")
	content := `
def scan_directory(project_path):
    return [{
        "func_name": "handle_scan",
        "file_path": project_path + "/src/http.c",
        "skill": "civetweb_audit",
        "start_line": 7,
    }]
`
	if err := os.WriteFile(scanPath, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	entries, err := RunPythonScan(context.Background(), scanPath, "/tmp/project")
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].FuncName != "handle_scan" {
		t.Fatalf("entry = %#v", entries[0])
	}
	if entries[0].StartLine == nil || *entries[0].StartLine != 7 {
		t.Fatalf("start_line = %#v", entries[0].StartLine)
	}
}

func TestRunPythonScanIncludesStderrOnFailure(t *testing.T) {
	dir := t.TempDir()
	scanPath := filepath.Join(dir, "scan.py")
	content := `
import sys
def scan_directory(project_path):
    print("scan exploded", file=sys.stderr)
    raise RuntimeError("boom")
`
	if err := os.WriteFile(scanPath, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	_, err := RunPythonScan(context.Background(), scanPath, "/tmp/project")
	if err == nil {
		t.Fatal("expected scan failure")
	}
	if got := err.Error(); got == "" || !containsAll(got, "scan exploded", "boom") {
		t.Fatalf("error did not include stderr and exception: %v", err)
	}
}

func containsAll(value string, needles ...string) bool {
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			return false
		}
	}
	return true
}
