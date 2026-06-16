package pipeline

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/config"
	"tsj-audit/internal/models"
	"tsj-audit/internal/runtime"
	"tsj-audit/internal/status"
)

func TestRunLoadsEntryCallsTraceAndSavesCheckpoint(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:     entryPath,
			OutputDir: outputDir,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if loaded.CodeLogic != "reads request" {
		t.Fatalf("checkpoint = %#v", loaded)
	}
	logPath := filepath.Join(outputDir, "checkpoints", "logs", "src_http_c_10_handle_request.jsonl")
	logData, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(logData), "starting trace") || !strings.Contains(string(logData), "function completed") {
		t.Fatalf("function log = %s", logData)
	}
}

func TestRunSavesCheckpointUsingDiscoveryEntryKey(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handleGet","file_path":"Dice/DiceManager.h","start_line":71}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"CustomMsgApiHandler::handleGet",
				"file_path":"Dice/DiceManager.h",
				"start_line":71,
				"end_line":99,
				"code_snippet":"bool handleGet() {}"
			},
			"code_logic":"reads messages",
			"code_map":[],
			"exploit_results":[]
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	store := checkpoint.Store{OutputDir: outputDir}
	got, ok, err := store.Load("Dice/DiceManager.h:71:handleGet")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint loaded by discovery key")
	}
	if got.FunctionInfo.FuncName != "CustomMsgApiHandler::handleGet" {
		t.Fatalf("trace function info should be preserved: %#v", got.FunctionInfo)
	}
	if _, err := os.Stat(filepath.Join(outputDir, "checkpoints", "Dice_DiceManager_h_71_handleGet.json")); err != nil {
		t.Fatal(err)
	}
}

func TestRunBackfillsTraceFunctionInfoFromEntry(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
	})

	if err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:     entryPath,
			OutputDir: outputDir,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	}); err != nil {
		t.Fatal(err)
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if loaded.FunctionInfo.FuncName != "handle_request" || loaded.FunctionInfo.FilePath != "src/http.c" || loaded.FunctionInfo.StartLine != 10 {
		t.Fatalf("function info = %#v", loaded.FunctionInfo)
	}
}

func TestRunProcessesFunctionsConcurrently(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[
		{"func_name":"handle_one","file_path":"src/one.c","start_line":10},
		{"func_name":"handle_two","file_path":"src/two.c","start_line":20}
	]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := &concurrentTraceRuntime{delay: 50 * time.Millisecond}
	if err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:               entryPath,
			OutputDir:           outputDir,
			FunctionConcurrency: 2,
			DisableExploit:      true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	}); err != nil {
		t.Fatal(err)
	}

	if client.MaxInflight() < 2 {
		t.Fatalf("max inflight = %d, want at least 2", client.MaxInflight())
	}
	store := checkpoint.Store{OutputDir: outputDir}
	for _, key := range []string{"src/one.c:10:handle_one", "src/two.c:20:handle_two"} {
		if _, ok, err := store.Load(key); err != nil {
			t.Fatal(err)
		} else if !ok {
			t.Fatalf("missing checkpoint %s", key)
		}
	}
}

func TestRunDoesNotOverwriteDuplicateFunctionNames(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[
		{"func_name":"handle","file_path":"src/one.c","start_line":10},
		{"func_name":"handle","file_path":"src/two.c","start_line":20}
	]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	if err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:               entryPath,
			OutputDir:           outputDir,
			FunctionConcurrency: 2,
			DisableExploit:      true,
		},
		Runtime:     &concurrentTraceRuntime{},
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	}); err != nil {
		t.Fatal(err)
	}

	all, err := checkpoint.Store{OutputDir: outputDir}.LoadAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != 2 {
		t.Fatalf("checkpoints = %#v", all)
	}
	for _, key := range []string{"src/one.c:10:handle", "src/two.c:20:handle"} {
		if _, ok := all[key]; !ok {
			t.Fatalf("missing %s in %#v", key, all)
		}
	}
}

func TestRunResumeSkipsExistingCheckpoint(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	store := checkpoint.Store{OutputDir: outputDir}
	if err := store.Save(traceResultForTest("handle_request")); err != nil {
		t.Fatal(err)
	}

	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{"unexpected":true}`),
	})
	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:     entryPath,
			OutputDir: outputDir,
			Resume:    true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: store,
	})
	if err != nil {
		t.Fatal(err)
	}
	if client.Calls("Trace") != 0 {
		t.Fatalf("Trace calls = %d, want 0", client.Calls("Trace"))
	}
}

func TestRunCallsAuditForConfiguredAuditTypes(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal": json.RawMessage(`{
			"is_vulnerable":true,
			"confidence":"high",
			"description":"path reaches fopen",
			"summary":"",
			"code_map":[],
			"findings":[]
		}`),
	})

	state := status.New()
	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"path_traversal"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      state,
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if len(loaded.AuditOutputs) != 1 {
		t.Fatalf("audit outputs = %#v", loaded.AuditOutputs)
	}
	if loaded.AuditOutputs[0].VulnerabilityType != "path_traversal" ||
		loaded.AuditOutputs[0].Output.Description != "path reaches fopen" {
		t.Fatalf("audit outputs = %#v", loaded.AuditOutputs)
	}
	snapshot := state.Snapshot()
	if snapshot.Stage != "Audit" || snapshot.AuditType != "path_traversal" || snapshot.FunctionName != "handle_request" {
		t.Fatalf("status snapshot = %#v", snapshot)
	}
}

func TestRunRejectsEmptyAuditDescription(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:password_reset": json.RawMessage(`{
			"is_vulnerable":false,
			"confidence":"",
			"description":"",
			"summary":"",
			"recommendation":null,
			"code_map":[],
			"findings":[]
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"password_reset"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err == nil || !strings.Contains(err.Error(), "empty description or confidence") {
		t.Fatalf("err = %v", err)
	}
}

func TestRunRetriesCodeContextOnlyAuditOutput(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMockWithSequences(map[string][]json.RawMessage{
		"Trace": {
			json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		},
		"Audit:brute_force": {
			json.RawMessage(`{
			"function_name":"handle_request",
			"file_path":"src/http.c",
			"line_start":10,
			"line_end":20,
			"code_snippet":"void handle_request() {}",
			"is_entry_point":true,
			"taint_source":"request url",
			"taint_path":"no credential check"
		}`),
			json.RawMessage(`{
			"is_vulnerable":false,
			"confidence":"high",
			"description":"no credential check",
			"summary":"not a brute force endpoint",
			"recommendation":null,
			"code_map":[],
			"findings":[]
		}`),
		},
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"brute_force"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok || len(loaded.AuditOutputs) != 1 {
		t.Fatalf("loaded = %#v ok=%v", loaded, ok)
	}
	result := loaded.AuditOutputs[0].Output
	if result.IsVulnerable || result.Confidence != "high" || result.Description != "no credential check" {
		t.Fatalf("audit output = %#v", result)
	}
	if client.Calls("Audit:brute_force") != 2 {
		t.Fatalf("Audit:brute_force calls = %d", client.Calls("Audit:brute_force"))
	}
}

func TestRunRecordsAuditErrorAfterRepeatedCodeContextOnlyOutput(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	malformed := json.RawMessage(`{
		"function_name":"handle_request",
		"file_path":"src/http.c",
		"line_start":10,
		"line_end":20,
		"code_snippet":"void handle_request() {}",
		"is_entry_point":true,
		"taint_source":"request url",
		"taint_path":"no credential check"
	}`)
	client := runtime.NewMockWithSequences(map[string][]json.RawMessage{
		"Trace": {
			json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		},
		"Audit:brute_force": {malformed, malformed, malformed},
		"Audit:loop": {
			json.RawMessage(`{
			"is_vulnerable":false,
			"confidence":"high",
			"description":"loop ok",
			"summary":"loop ok",
			"recommendation":null,
			"code_map":[],
			"findings":[]
		}`),
		},
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"brute_force", "loop"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}
	if client.Calls("Audit:brute_force") != 3 {
		t.Fatalf("Audit:brute_force calls = %d", client.Calls("Audit:brute_force"))
	}
	if client.Calls("Audit:loop") != 1 {
		t.Fatalf("Audit:loop calls = %d", client.Calls("Audit:loop"))
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok || len(loaded.AuditOutputs) != 2 {
		t.Fatalf("loaded = %#v ok=%v", loaded, ok)
	}
	if loaded.AuditOutputs[0].VulnerabilityType != "brute_force" ||
		loaded.AuditOutputs[0].Output.Confidence != "error" ||
		!strings.Contains(loaded.AuditOutputs[0].Output.Description, "returned code context without structured vulnerability verdict after 3 attempts") {
		t.Fatalf("error audit output = %#v", loaded.AuditOutputs[0])
	}
	if loaded.AuditOutputs[1].VulnerabilityType != "loop" || loaded.AuditOutputs[1].Output.Description != "loop ok" {
		t.Fatalf("next audit did not continue = %#v", loaded.AuditOutputs)
	}

	logData, err := os.ReadFile(filepath.Join(outputDir, "checkpoints", "logs", "src_http_c_10_handle_request.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(logData), "audit error: audit brute_force returned code context without structured vulnerability verdict after 3 attempts") {
		t.Fatalf("log missing audit error: %s", string(logData))
	}
}

func TestRunCallsExploitForMediumAndHighConfidenceFindings(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:command_injection": json.RawMessage(`{
			"is_vulnerable":true,
			"confidence":"medium",
			"description":"command reaches system",
			"summary":"",
			"code_map":[],
			"findings":[{
				"title":"command reaches system",
				"is_vulnerable":true,
				"confidence":"medium",
				"description":"command reaches system",
				"code_map":[]
			}]
		}`),
		"Exploit:command_injection": json.RawMessage(`{
			"success":false,
			"poc_command":"curl http://target/",
			"summary":"mock",
			"error":null
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"command_injection"},
			DisableExploit: false,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("src/http.c:10:handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if len(loaded.ExploitResult) != 1 {
		t.Fatalf("exploit results = %#v", loaded.ExploitResult)
	}
	if loaded.ExploitResult[0].VulnerabilityType != "command_injection" {
		t.Fatalf("exploit results = %#v", loaded.ExploitResult)
	}
}

func TestRunUsesRequiredAuditTypesFromEntrySkill(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","skill":"civetweb_audit","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:command_injection": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:brute_force":       json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:password_reset":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:loop":              json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	for _, auditType := range []string{"command_injection", "path_traversal", "brute_force", "password_reset", "loop"} {
		if client.Calls("Audit:"+auditType) != 1 {
			t.Fatalf("Audit:%s calls = %d, want 1", auditType, client.Calls("Audit:"+auditType))
		}
	}
}

func TestRunInjectsSkillUsageIntoTracePrompt(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","skill":"civetweb_audit","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}",
				"skill":"civetweb_audit"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:command_injection": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:brute_force":       json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:password_reset":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:loop":              json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	requests := client.Requests("Trace")
	if len(requests) != 1 {
		t.Fatalf("trace requests = %#v", requests)
	}
	if !strings.Contains(requests[0].UserPrompt, "Attack Surface Skill") || !strings.Contains(requests[0].UserPrompt, "civetweb_audit") {
		t.Fatalf("trace prompt missing skill usage:\n%s", requests[0].UserPrompt)
	}
}

func TestRunPassesSchemasToRuntimeStages(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"path_traversal"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	for _, stage := range []string{"Trace", "Audit:path_traversal"} {
		requests := client.Requests(stage)
		if len(requests) != 1 {
			t.Fatalf("%s requests = %#v", stage, requests)
		}
		if len(requests[0].Schema) == 0 {
			t.Fatalf("%s missing schema", stage)
		}
	}
}

func TestRunSavesFunctionConversations(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal": json.RawMessage(`{
			"is_vulnerable":false,
			"confidence":"high",
			"description":"No path traversal because no filesystem path is built from input.",
			"summary":"No path traversal because no filesystem path is built from input.",
			"code_map":[],
			"findings":[]
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:          entryPath,
			OutputDir:      outputDir,
			AuditTypes:     []string{"path_traversal"},
			DisableExploit: true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	conversationDir := filepath.Join(outputDir, "checkpoints", "conversations", "src_http_c_10_handle_request")
	entries, err := os.ReadDir(conversationDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 2 {
		t.Fatalf("conversation files = %d, want 2", len(entries))
	}
	seen := map[string]bool{}
	for _, entry := range entries {
		data, err := os.ReadFile(filepath.Join(conversationDir, entry.Name()))
		if err != nil {
			t.Fatal(err)
		}
		var got checkpoint.ConversationEntry
		if err := json.Unmarshal(data, &got); err != nil {
			t.Fatal(err)
		}
		if got.EntryKey != "src/http.c:10:handle_request" || got.Request.UserPrompt == "" || len(got.Request.Schema) == 0 || len(got.Response.Raw) == 0 {
			t.Fatalf("conversation = %#v", got)
		}
		seen[got.StageName] = true
	}
	if !seen["Trace"] || !seen["Audit:path_traversal"] {
		t.Fatalf("stages = %#v", seen)
	}
}

func TestRunAddsFallbackAuditWhenEnabled(t *testing.T) {
	dir := t.TempDir()
	entryPath := filepath.Join(dir, "entries.json")
	entryJSON := `[{"func_name":"handle_request","file_path":"src/http.c","start_line":10}]`
	if err := os.WriteFile(entryPath, []byte(entryJSON), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"handle_request",
				"file_path":"src/http.c",
				"start_line":10,
				"end_line":20,
				"code_snippet":"void handle_request() {}"
			},
			"code_logic":"reads request",
			"code_map":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","findings":[]}`),
		"Audit:fallback_security": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"fallback none","summary":"fallback none","findings":[]}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			Entry:               entryPath,
			OutputDir:           outputDir,
			AuditTypes:          []string{"path_traversal"},
			EnableFallbackAudit: true,
			DisableExploit:      true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}
	if client.Calls("Audit:fallback_security") != 1 {
		t.Fatalf("fallback calls = %d, want 1", client.Calls("Audit:fallback_security"))
	}
}

func TestRunAttackSurfaceSkillUsesBundledScanScriptAndSavesDiscoveredEntries(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	if err := os.MkdirAll(projectDir, 0755); err != nil {
		t.Fatal(err)
	}
	outputDir := filepath.Join(dir, "output")
	client := runtime.NewEchoTraceMock()

	err := Run(context.Background(), Options{
		Config: config.Config{
			ProjectPath:        projectDir,
			OutputDir:          outputDir,
			AttackSurfaceSkill: "civetweb_audit",
			DisableExploit:     true,
			AuditTypes:         []string{},
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}

	discoveredPath := filepath.Join(outputDir, "discovered_functions.json")
	if _, err := os.Stat(discoveredPath); err != nil {
		t.Fatalf("expected discovered entries at %s: %v", discoveredPath, err)
	}
}

func TestRunAttackSurfaceSkillFallsBackToRuntimeDiscovery(t *testing.T) {
	dir := t.TempDir()
	projectDir := filepath.Join(dir, "project")
	skillDir := filepath.Join(projectDir, "skills", "attack_surface", "custom_surface")
	if err := os.MkdirAll(skillDir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(skillDir, "SKILL.md"), []byte("---\nname: custom_surface\n---\n# Custom\n"), 0644); err != nil {
		t.Fatal(err)
	}

	outputDir := filepath.Join(dir, "output")
	client := runtime.NewMock(map[string]json.RawMessage{
		"EntryDiscovery": json.RawMessage(`{"functions":[{"func_name":"runtime_entry","file_path":"src/runtime.c","skill":"custom_surface","start_line":4}]}`),
		"Trace": json.RawMessage(`{
			"function_info":{
				"func_name":"runtime_entry",
				"file_path":"src/runtime.c",
				"start_line":4,
				"end_line":8,
				"code_snippet":"void runtime_entry() {}",
				"skill":"custom_surface"
			},
			"code_logic":"runtime discovery",
			"code_map":[],
			"exploit_results":[]
		}`),
	})

	err := Run(context.Background(), Options{
		Config: config.Config{
			ProjectPath:        projectDir,
			OutputDir:          outputDir,
			AttackSurfaceSkill: "custom_surface",
			DisableExploit:     true,
		},
		Runtime:     client,
		Status:      status.New(),
		Checkpoints: checkpoint.Store{OutputDir: outputDir},
	})
	if err != nil {
		t.Fatal(err)
	}
	if client.Calls("EntryDiscovery") != 1 {
		t.Fatalf("EntryDiscovery calls = %d, want 1", client.Calls("EntryDiscovery"))
	}
	if _, err := os.Stat(filepath.Join(outputDir, "discovered_functions.json")); err != nil {
		t.Fatal(err)
	}
}

func traceResultForTest(funcName string) models.TraceResult {
	return models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:    funcName,
			FilePath:    "src/http.c",
			StartLine:   10,
			EndLine:     20,
			CodeSnippet: "void handle_request() {}",
		},
		CodeLogic: "existing checkpoint",
	}
}

type concurrentTraceRuntime struct {
	mu       sync.Mutex
	inflight int
	max      int
	delay    time.Duration
}

func (r *concurrentTraceRuntime) RunJSON(ctx context.Context, req runtime.RunJSONRequest) (json.RawMessage, []runtime.Message, error) {
	r.mu.Lock()
	r.inflight++
	if r.inflight > r.max {
		r.max = r.inflight
	}
	r.mu.Unlock()
	defer func() {
		r.mu.Lock()
		r.inflight--
		r.mu.Unlock()
	}()
	if r.delay > 0 {
		select {
		case <-ctx.Done():
			return nil, nil, ctx.Err()
		case <-time.After(r.delay):
		}
	}
	raw := json.RawMessage(`{
		"function_info":{
			"end_line":30,
			"code_snippet":"void handle() {}"
		},
		"code_logic":"concurrent trace",
		"code_map":[],
		"exploit_results":[]
	}`)
	return raw, []runtime.Message{{Role: "assistant", Content: string(raw)}}, nil
}

func (r *concurrentTraceRuntime) MaxInflight() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.max
}
