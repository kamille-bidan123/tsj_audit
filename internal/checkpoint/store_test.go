package checkpoint

import (
	"os"
	"path/filepath"
	"testing"

	"tsj-audit/internal/models"
)

func TestSaveAndLoadCheckpoint(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:    "Class::handle/request",
			FilePath:    "src/http.c",
			StartLine:   1,
			EndLine:     3,
			CodeSnippet: "void handle() {}",
		},
		CodeLogic: "logic",
	}

	if err := store.Save(result); err != nil {
		t.Fatal(err)
	}

	path := filepath.Join(store.OutputDir, "checkpoints", "Class__handle_request.json")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected checkpoint at %s: %v", path, err)
	}

	got, ok, err := store.Load("Class::handle/request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if got.FunctionInfo.FuncName != result.FunctionInfo.FuncName {
		t.Fatalf("got = %#v", got)
	}
}

func TestLoadAllCheckpoints(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	if err := store.Save(models.TraceResult{FunctionInfo: models.FunctionInfo{FuncName: "one", FilePath: "a.c"}}); err != nil {
		t.Fatal(err)
	}
	if err := store.Save(models.TraceResult{FunctionInfo: models.FunctionInfo{FuncName: "two", FilePath: "b.c"}}); err != nil {
		t.Fatal(err)
	}

	all, err := store.LoadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != 2 {
		t.Fatalf("all = %#v", all)
	}
	if _, ok := all["one"]; !ok {
		t.Fatalf("missing one in %#v", all)
	}
}

func TestLoadMissingCheckpoint(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	_, ok, err := store.Load("missing")
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Fatal("expected missing checkpoint")
	}
}
