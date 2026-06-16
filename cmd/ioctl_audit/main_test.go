package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"tsj-audit/internal/models"
)

func TestRunScansIOCTLProject(t *testing.T) {
	project := t.TempDir()
	source := `#include <linux/fs.h>
static long binary_ioctl(struct file *file, unsigned int cmd, unsigned long arg) {
	return 0;
}
static const struct file_operations fops = {
	.unlocked_ioctl = binary_ioctl,
};
`
	writeCommandTestFile(t, project, "drivers/dev.c", source)

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	if code := run([]string{project}, &stdout, &stderr); code != 0 {
		t.Fatalf("exit code = %d stderr=%s", code, stderr.String())
	}

	var entries []models.EntrySpec
	if err := json.Unmarshal(stdout.Bytes(), &entries); err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].FuncName != "binary_ioctl" {
		t.Fatalf("entries = %#v", entries)
	}
}

func writeCommandTestFile(t *testing.T, root string, rel string, content string) {
	t.Helper()
	path := filepath.Join(root, rel)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}
