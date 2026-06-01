package pipeline

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

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
			"audit_results":[],
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

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if loaded.CodeLogic != "reads request" {
		t.Fatalf("checkpoint = %#v", loaded)
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
			"audit_results":[],
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

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("handle_request")
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected checkpoint")
	}
	if len(loaded.AuditResults) != 1 {
		t.Fatalf("audit results = %#v", loaded.AuditResults)
	}
	if loaded.AuditResults[0].VulnerabilityType != "path_traversal" {
		t.Fatalf("audit results = %#v", loaded.AuditResults)
	}
	snapshot := state.Snapshot()
	if snapshot.Stage != "Audit" || snapshot.AuditType != "path_traversal" || snapshot.FunctionName != "handle_request" {
		t.Fatalf("status snapshot = %#v", snapshot)
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
			"audit_results":[],
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

	loaded, ok, err := checkpoint.Store{OutputDir: outputDir}.Load("handle_request")
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
			"audit_results":[],
			"exploit_results":[]
		}`),
		"Audit:command_injection": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:brute_force":       json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:password_reset":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:loop":              json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
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
			"audit_results":[],
			"exploit_results":[]
		}`),
		"Audit:command_injection": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:brute_force":       json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:password_reset":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:loop":              json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
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
			"audit_results":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
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
			"audit_results":[],
			"exploit_results":[]
		}`),
		"Audit:path_traversal":    json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"none","summary":"none","code_map":[],"findings":[]}`),
		"Audit:fallback_security": json.RawMessage(`{"is_vulnerable":false,"confidence":"low","description":"fallback none","summary":"fallback none","code_map":[],"findings":[]}`),
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
			"audit_results":[],
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
