package export

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/models"
)

func TestWriteReportsFromCheckpoints(t *testing.T) {
	outputDir := t.TempDir()
	store := checkpoint.Store{OutputDir: outputDir}
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:    "handle_request",
			FilePath:    "src/http.c",
			StartLine:   10,
			EndLine:     20,
			CodeSnippet: "void handle_request() {}",
		},
		CodeLogic: "reads request path",
		AuditResults: []models.AuditResult{
			{
				VulnerabilityType: "path_traversal",
				Title:             models.StringPtr("unsafe file path"),
				Severity:          models.StringPtr("high"),
				IsVulnerable:      true,
				Confidence:        "high",
				Description:       "external path reaches fopen",
				TaintFlow:         models.StringPtr("request.path -> fopen"),
				Recommendation:    models.StringPtr("normalize and constrain paths"),
				CodeMap: []models.CodeContext{
					{
						FunctionName: "handle_request",
						FilePath:     "src/http.c",
						LineStart:    10,
						LineEnd:      20,
						CodeSnippet:  "fopen(path)",
						IsEntryPoint: true,
					},
				},
			},
		},
		ExploitResult: []models.ExploitResult{
			{
				VulnerabilityType: "path_traversal",
				Success:           false,
				PocCommand:        "curl http://target/file",
				Output:            "blocked",
			},
		},
	}
	if err := store.Save(result); err != nil {
		t.Fatal(err)
	}

	artifacts, err := WriteReports(outputDir)
	if err != nil {
		t.Fatal(err)
	}

	for _, path := range []string{artifacts.JSONPath, artifacts.MarkdownPath, artifacts.HTMLPath, artifacts.SARIFPath, artifacts.IssuesSARIF} {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("expected report %s: %v", path, err)
		}
	}

	markdown, err := os.ReadFile(filepath.Join(outputDir, "audit_report.md"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(markdown)
	for _, needle := range []string{"# TSJ Audit Report", "Vulnerable findings: 1", "Severity high: 1", "handle_request", "path_traversal", "external path reaches fopen", "request.path -> fopen", "normalize and constrain paths", "src/http.c:10-20", "curl http://target/file"} {
		if !strings.Contains(text, needle) {
			t.Fatalf("markdown missing %q:\n%s", needle, text)
		}
	}

	html, err := os.ReadFile(filepath.Join(outputDir, "audit_report.html"))
	if err != nil {
		t.Fatal(err)
	}
	htmlText := string(html)
	for _, needle := range []string{"<!doctype html>", "TSJ Audit Report", "Vulnerable findings: 1", "Severity high: 1", "handle_request", "path_traversal", "request.path -&gt; fopen", "curl http://target/file"} {
		if !strings.Contains(htmlText, needle) {
			t.Fatalf("html missing %q:\n%s", needle, htmlText)
		}
	}

	sarif, err := os.ReadFile(filepath.Join(outputDir, "audit_report.sarif"))
	if err != nil {
		t.Fatal(err)
	}
	sarifText := string(sarif)
	for _, needle := range []string{`"version": "2.1.0"`, `"ruleId": "path_traversal"`, `"level": "error"`, `"uri": "src/http.c"`, `"startLine": 10`} {
		if !strings.Contains(sarifText, needle) {
			t.Fatalf("sarif missing %q:\n%s", needle, sarifText)
		}
	}
	var sarifDoc map[string]any
	if err := json.Unmarshal(sarif, &sarifDoc); err != nil {
		t.Fatal(err)
	}
	taintFlow, ok := sarifDoc["runs"].([]any)[0].(map[string]any)["results"].([]any)[0].(map[string]any)["codeFlows"].([]any)[0].(map[string]any)["threadFlows"].([]any)[0].(map[string]any)["locations"].([]any)[0].(map[string]any)["location"].(map[string]any)["message"].(map[string]any)["text"].(string)
	if !ok || taintFlow != "request.path -> fopen" {
		t.Fatalf("sarif taint flow = %#v", taintFlow)
	}

	issues, err := os.ReadFile(filepath.Join(outputDir, "audit_issues.sarif"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(issues), `"ruleId": "path_traversal"`) {
		t.Fatalf("issues sarif missing vulnerable finding:\n%s", string(issues))
	}
}
