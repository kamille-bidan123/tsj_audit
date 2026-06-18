package checkpoint

import (
	"encoding/json"
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

	key := result.FunctionInfo.Key()
	path := filepath.Join(store.OutputDir, "checkpoints", "src_http_c_1_Class__handle_request.json")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected checkpoint at %s: %v", path, err)
	}

	got, ok, err := store.Load(key)
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

func TestSaveForKeyUsesDiscoveryEntryKey(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	entryKey := "Dice/DiceManager.h:71:handleGet"
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:    "CustomMsgApiHandler::handleGet",
			FilePath:    "Dice/DiceManager.h",
			StartLine:   71,
			EndLine:     99,
			CodeSnippet: "bool handleGet() {}",
		},
		CodeLogic: "logic",
	}

	if err := store.SaveForKey(entryKey, result); err != nil {
		t.Fatal(err)
	}

	path := filepath.Join(store.OutputDir, "checkpoints", "Dice_DiceManager_h_71_handleGet.json")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected checkpoint at discovery key path %s: %v", path, err)
	}
	if _, err := os.Stat(filepath.Join(store.OutputDir, "checkpoints", "Dice_DiceManager_h_71_CustomMsgApiHandler__handleGet.json")); !os.IsNotExist(err) {
		t.Fatalf("checkpoint should not be saved under trace function key, stat err=%v", err)
	}

	got, ok, err := store.Load(entryKey)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint loaded by discovery key")
	}
	if got.FunctionInfo.FuncName != "CustomMsgApiHandler::handleGet" {
		t.Fatalf("function info should preserve trace name: %#v", got.FunctionInfo)
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
	if _, ok := all["a.c:0:one"]; !ok {
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

func TestAppendFunctionLogWritesJSONLUnderCheckpoints(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	entry := FunctionLogEntry{
		Time:     "2026-06-04T00:00:00Z",
		EntryKey: "src/http.c:10:handle",
		Stage:    "Audit",
		Message:  "tool completed",
	}

	if err := store.AppendFunctionLog(entry); err != nil {
		t.Fatal(err)
	}

	path := filepath.Join(store.OutputDir, "checkpoints", "logs", "src_http_c_10_handle.jsonl")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var got FunctionLogEntry
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}
	if got.EntryKey != entry.EntryKey || got.Message != entry.Message {
		t.Fatalf("log entry = %#v", got)
	}
}

func TestSaveConversationWritesFunctionTranscript(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	entry := ConversationEntry{
		Time:      "2026-06-04T00:00:00Z",
		EntryKey:  "src/http.c:10:handle",
		StageName: "Audit:path_traversal",
		Request: ConversationRequest{
			UserPrompt: `{"func_name":"handle"}`,
			Schema:     json.RawMessage(`{"type":"object"}`),
		},
		Response: ConversationResponse{
			Raw:     json.RawMessage(`{"ok":true}`),
			Payload: json.RawMessage(`{"ok":true}`),
			Messages: []ConversationMessage{
				{Role: "assistant", Content: `{"ok":true}`},
			},
		},
	}

	path, err := store.SaveConversation(entry)
	if err != nil {
		t.Fatal(err)
	}
	if filepath.Dir(path) != filepath.Join(store.OutputDir, "checkpoints", "conversations", "src_http_c_10_handle") {
		t.Fatalf("path = %s", path)
	}

	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var got ConversationEntry
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}
	var raw map[string]bool
	if err := json.Unmarshal(got.Response.Raw, &raw); err != nil {
		t.Fatal(err)
	}
	if got.EntryKey != entry.EntryKey || got.StageName != entry.StageName || !raw["ok"] {
		t.Fatalf("conversation = %#v", got)
	}
}

func TestSaveConversationOmitsEmptyRawMessages(t *testing.T) {
	store := Store{OutputDir: t.TempDir()}
	entry := ConversationEntry{
		Time:      "2026-06-04T00:00:00Z",
		EntryKey:  "src/http.c:10:handle",
		StageName: "Trace",
		Request: ConversationRequest{
			UserPrompt: `{"func_name":"handle"}`,
			Schema:     json.RawMessage(" \n"),
		},
		Response: ConversationResponse{
			Raw:     json.RawMessage(" \n"),
			Payload: json.RawMessage(" \n"),
		},
		Error: "claudecode runtime failed",
	}

	path, err := store.SaveConversation(entry)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	request := raw["request"].(map[string]interface{})
	if _, ok := request["schema"]; ok {
		t.Fatalf("schema should be omitted from %s", data)
	}
	response := raw["response"].(map[string]interface{})
	if _, ok := response["raw"]; ok {
		t.Fatalf("raw should be omitted from %s", data)
	}
	if _, ok := response["payload"]; ok {
		t.Fatalf("payload should be omitted from %s", data)
	}
}
