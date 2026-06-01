package models

import (
	"encoding/json"
	"testing"
)

func TestEntrySpecJSONRoundTrip(t *testing.T) {
	input := EntrySpec{
		FuncName:  "handle_request",
		FilePath:  "src/http.c",
		Skill:     StringPtr("civetweb_audit"),
		StartLine: IntPtr(42),
	}

	data, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}

	var got EntrySpec
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}

	if got.FuncName != input.FuncName || got.FilePath != input.FilePath {
		t.Fatalf("round trip mismatch: %#v", got)
	}
	if got.Skill == nil || *got.Skill != "civetweb_audit" {
		t.Fatalf("skill mismatch: %#v", got.Skill)
	}
	if got.StartLine == nil || *got.StartLine != 42 {
		t.Fatalf("start_line mismatch: %#v", got.StartLine)
	}
}

func TestTraceResultJSONShape(t *testing.T) {
	result := TraceResult{
		FunctionInfo: FunctionInfo{
			FuncName:    "handle_request",
			FilePath:    "src/http.c",
			StartLine:   10,
			EndLine:     20,
			CodeSnippet: "void handle_request() {}",
		},
		CodeLogic: "reads request path",
		CodeMap: []CodeContext{
			{
				FunctionName: "handle_request",
				FilePath:     "src/http.c",
				LineStart:    10,
				LineEnd:      20,
				CodeSnippet:  "void handle_request() {}",
				IsEntryPoint: true,
			},
		},
		AuditResults: []AuditResult{
			{
				VulnerabilityType: "path_traversal",
				IsVulnerable:      true,
				Confidence:        "high",
				Description:       "unsanitized path reaches file open",
			},
		},
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"function_info", "code_logic", "code_map", "audit_results", "exploit_results"} {
		if _, ok := decoded[key]; !ok {
			t.Fatalf("expected %q key in %s", key, string(data))
		}
	}
}
