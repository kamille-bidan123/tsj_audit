package scanner

import (
	"os"
	"path/filepath"
	"testing"
)

func TestValidateEntrySourcesRequiresExactlyOneSource(t *testing.T) {
	if err := ValidateEntrySources("", "", ""); err == nil {
		t.Fatal("expected no source error")
	}
	if err := ValidateEntrySources("scan.py", "entries.json", ""); err == nil {
		t.Fatal("expected mutually exclusive source error")
	}
	if err := ValidateEntrySources("", "entries.json", ""); err != nil {
		t.Fatal(err)
	}
}

func TestLoadEntrySpecs(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "entries.json")
	content := `[{"func_name":"handle","file_path":"src/http.c","skill":"civetweb_audit","start_line":12}]`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	entries, err := LoadEntrySpecs(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].FuncName != "handle" || entries[0].FilePath != "src/http.c" {
		t.Fatalf("entry = %#v", entries[0])
	}
	if entries[0].Skill == nil || *entries[0].Skill != "civetweb_audit" {
		t.Fatalf("skill = %#v", entries[0].Skill)
	}
	if entries[0].StartLine == nil || *entries[0].StartLine != 12 {
		t.Fatalf("start_line = %#v", entries[0].StartLine)
	}
}

func TestLoadEntrySpecsRejectsNonJSON(t *testing.T) {
	_, err := LoadEntrySpecs(filepath.Join(t.TempDir(), "entries.txt"))
	if err == nil {
		t.Fatal("expected non-json error")
	}
}
