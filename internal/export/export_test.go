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
		AuditOutputs: []models.AuditStageOutput{
			{
				VulnerabilityType: "path_traversal",
				Output: models.AuditOutput{
					IsVulnerable: true,
					Confidence:   "high",
					Description:  "external path reaches fopen",
					Summary:      "external path reaches fopen",
					Findings: []models.AuditFindingOutput{
						{
							Title:          "unsafe file path",
							Severity:       models.StringPtr("high"),
							IsVulnerable:   true,
							Confidence:     "high",
							Description:    "external path reaches fopen",
							Recommendation: models.StringPtr("normalize and constrain paths"),
							PrimaryLocation: models.FindingLocation{
								Message:      "external path reaches fopen",
								FunctionName: "handle_request",
								FilePath:     "src/http.c",
								LineStart:    10,
								LineEnd:      20,
							},
							DataFlows: testFindingDataFlows(),
						},
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
	for _, needle := range []string{"# TSJ Audit Report", "Vulnerable findings: 1", "Severity high: 1", "handle_request", "path_traversal", "external path reaches fopen", "request path flows into fopen", "normalize and constrain paths", "src/http.c:18-20", "curl http://target/file"} {
		if !strings.Contains(text, needle) {
			t.Fatalf("markdown missing %q:\n%s", needle, text)
		}
	}

	html, err := os.ReadFile(filepath.Join(outputDir, "audit_report.html"))
	if err != nil {
		t.Fatal(err)
	}
	htmlText := string(html)
	for _, needle := range []string{"<!doctype html>", "TSJ Audit Report", "Vulnerable findings: 1", "Severity high: 1", "handle_request", "path_traversal", "request path flows into fopen", "curl http://target/file"} {
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
	firstStepMessage, ok := sarifDoc["runs"].([]any)[0].(map[string]any)["results"].([]any)[0].(map[string]any)["codeFlows"].([]any)[0].(map[string]any)["threadFlows"].([]any)[0].(map[string]any)["locations"].([]any)[0].(map[string]any)["location"].(map[string]any)["message"].(map[string]any)["text"].(string)
	if !ok || firstStepMessage != "request path is read from HTTP input" {
		t.Fatalf("sarif first step = %#v", firstStepMessage)
	}

	issues, err := os.ReadFile(filepath.Join(outputDir, "audit_issues.sarif"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(issues), `"ruleId": "path_traversal"`) {
		t.Fatalf("issues sarif missing vulnerable finding:\n%s", string(issues))
	}
}

func TestWriteReportsReadsLegacyAuditResults(t *testing.T) {
	outputDir := t.TempDir()
	checkpointDir := filepath.Join(outputDir, "checkpoints")
	if err := os.MkdirAll(checkpointDir, 0755); err != nil {
		t.Fatal(err)
	}
	legacy := `{
		"function_info":{
			"func_name":"handle_request",
			"file_path":"src/http.c",
			"start_line":10,
			"end_line":20,
			"code_snippet":""
		},
		"code_logic":"reads request path",
		"code_map":[],
		"audit_results":[
			{
				"vulnerability_type":"path_traversal",
				"is_vulnerable":true,
				"confidence":"high",
				"description":"legacy path traversal",
				"code_map":[
					{"function_name":"handle_request","file_path":"src/http.c","line_start":10,"line_end":20,"code_snippet":"","is_entry_point":true}
				]
			}
		],
		"exploit_results":[]
	}`
	if err := os.WriteFile(filepath.Join(checkpointDir, "legacy.json"), []byte(legacy), 0644); err != nil {
		t.Fatal(err)
	}

	artifacts, err := WriteReports(outputDir)
	if err != nil {
		t.Fatal(err)
	}
	sarif, err := os.ReadFile(artifacts.SARIFPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(sarif), "legacy path traversal") {
		t.Fatalf("legacy finding missing from sarif:\n%s", string(sarif))
	}
	report, err := os.ReadFile(artifacts.JSONPath)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(report), `"audit_results"`) {
		t.Fatalf("new JSON report should not write legacy audit_results:\n%s", string(report))
	}
}

func TestWriteReportsExpandsRawAuditOutputsForSARIF(t *testing.T) {
	outputDir := t.TempDir()
	store := checkpoint.Store{OutputDir: outputDir}
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:  "handle_request",
			FilePath:  "src/http.c",
			StartLine: 10,
			EndLine:   20,
		},
		AuditOutputs: []models.AuditStageOutput{
			{
				VulnerabilityType: "path_traversal",
				Output: models.AuditOutput{
					IsVulnerable: true,
					Confidence:   "high",
					Description:  "top-level summary",
					Summary:      "top-level summary",
					Findings: []models.AuditFindingOutput{
						{
							Title:          "unsafe file path",
							Severity:       models.StringPtr("high"),
							IsVulnerable:   true,
							Confidence:     "high",
							Description:    "external path reaches fopen",
							Recommendation: models.StringPtr("normalize and constrain paths"),
							PrimaryLocation: models.FindingLocation{
								Message:      "external path reaches fopen",
								FunctionName: "handle_request",
								FilePath:     "src/http.c",
								LineStart:    12,
								LineEnd:      14,
							},
							DataFlows: testFindingDataFlows(),
						},
					},
				},
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

	sarif, err := os.ReadFile(artifacts.SARIFPath)
	if err != nil {
		t.Fatal(err)
	}
	var sarifDoc map[string]any
	if err := json.Unmarshal(sarif, &sarifDoc); err != nil {
		t.Fatal(err)
	}
	results := sarifDoc["runs"].([]any)[0].(map[string]any)["results"].([]any)
	if len(results) != 1 {
		t.Fatalf("sarif results = %#v", results)
	}
	first := results[0].(map[string]any)
	if first["ruleId"] != "path_traversal" {
		t.Fatalf("sarif result = %#v", first)
	}
	message := first["message"].(map[string]any)["text"].(string)
	if !strings.Contains(message, "unsafe file path") || !strings.Contains(message, "external path reaches fopen") {
		t.Fatalf("message = %q", message)
	}
	location := first["locations"].([]any)[0].(map[string]any)["physicalLocation"].(map[string]any)
	region := location["region"].(map[string]any)
	if region["startLine"] != float64(12) {
		t.Fatalf("region = %#v", region)
	}
}

func TestWriteReportsMapsFindingDataFlowsToSARIFThreadFlowLocations(t *testing.T) {
	outputDir := t.TempDir()
	store := checkpoint.Store{OutputDir: outputDir}
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:  "handle_request",
			FilePath:  "src/http.c",
			StartLine: 10,
			EndLine:   20,
		},
		AuditOutputs: []models.AuditStageOutput{
			{
				VulnerabilityType: "path_traversal",
				Output: models.AuditOutput{
					IsVulnerable: true,
					Confidence:   "high",
					Description:  "external path reaches fopen",
					Summary:      "external path reaches fopen",
					Findings: []models.AuditFindingOutput{
						{
							Title:          "unsafe file path",
							Severity:       models.StringPtr("high"),
							IsVulnerable:   true,
							Confidence:     "high",
							Description:    "external path reaches fopen",
							Recommendation: models.StringPtr("normalize and constrain paths"),
							PrimaryLocation: models.FindingLocation{
								Message:      "path reaches fopen",
								FunctionName: "open_file",
								FilePath:     "src/file.c",
								LineStart:    30,
								LineEnd:      32,
							},
							DataFlows: []models.FindingDataFlow{
								{
									Message: "request path flows into fopen",
									Steps: []models.FindingDataFlowStep{
										{
											Role:       "source",
											Message:    "request path is read from HTTP input",
											FilePath:   "src/http.c",
											LineStart:  10,
											LineEnd:    12,
											Importance: "essential",
										},
										{
											Role:       "sink",
											Message:    "path reaches fopen",
											FilePath:   "src/file.c",
											LineStart:  30,
											LineEnd:    32,
											Importance: "essential",
										},
									},
								},
							},
						},
					},
				},
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

	sarif, err := os.ReadFile(artifacts.SARIFPath)
	if err != nil {
		t.Fatal(err)
	}
	var sarifDoc map[string]any
	if err := json.Unmarshal(sarif, &sarifDoc); err != nil {
		t.Fatal(err)
	}
	resultNode := sarifDoc["runs"].([]any)[0].(map[string]any)["results"].([]any)[0].(map[string]any)
	primary := resultNode["locations"].([]any)[0].(map[string]any)["physicalLocation"].(map[string]any)
	if primary["artifactLocation"].(map[string]any)["uri"] != "src/file.c" {
		t.Fatalf("primary location = %#v", primary)
	}
	steps := resultNode["codeFlows"].([]any)[0].(map[string]any)["threadFlows"].([]any)[0].(map[string]any)["locations"].([]any)
	if len(steps) != 2 {
		t.Fatalf("steps = %#v", steps)
	}
	first := steps[0].(map[string]any)
	if first["executionOrder"] != float64(1) || first["kinds"].([]any)[0] != "source" {
		t.Fatalf("first step = %#v", first)
	}
	second := steps[1].(map[string]any)
	if second["executionOrder"] != float64(2) || second["kinds"].([]any)[0] != "sink" {
		t.Fatalf("second step = %#v", second)
	}
}

func TestWriteReportsInheritsSARIFExplorerReviewNotes(t *testing.T) {
	outputDir := t.TempDir()
	store := checkpoint.Store{OutputDir: outputDir}
	result := models.TraceResult{
		FunctionInfo: models.FunctionInfo{
			FuncName:  "handle_request",
			FilePath:  "src/http.c",
			StartLine: 10,
			EndLine:   20,
		},
		AuditOutputs: []models.AuditStageOutput{
			{
				VulnerabilityType: "command_injection",
				Output: models.AuditOutput{
					IsVulnerable: true,
					Confidence:   "medium",
					Description:  "other finding",
					Summary:      "other finding",
					Findings: []models.AuditFindingOutput{
						{
							Title:        "other finding",
							Severity:     models.StringPtr("medium"),
							IsVulnerable: true,
							Confidence:   "medium",
							Description:  "other finding",
						},
					},
				},
			},
			{
				VulnerabilityType: "path_traversal",
				Output: models.AuditOutput{
					IsVulnerable: true,
					Confidence:   "high",
					Description:  "external path reaches fopen",
					Summary:      "external path reaches fopen",
					Findings: []models.AuditFindingOutput{
						{
							Title:        "external path reaches fopen",
							Severity:     models.StringPtr("high"),
							IsVulnerable: true,
							Confidence:   "high",
							Description:  "external path reaches fopen",
							PrimaryLocation: models.FindingLocation{
								Message:      "external path reaches fopen",
								FunctionName: "handle_request",
								FilePath:     "src/http.c",
								LineStart:    10,
								LineEnd:      20,
							},
							DataFlows: testFindingDataFlows(),
						},
					},
				},
			},
		},
	}
	if err := store.Save(result); err != nil {
		t.Fatal(err)
	}

	oldSARIF := filepath.Join(outputDir, "reviewed.sarif")
	oldSARIFText := `{
  "version": "2.1.0",
  "runs": [
    {
      "results": [
        {
          "ruleId": "path_traversal",
          "message": {"text": "external path reaches fopen: external path reaches fopen"},
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {"uri": "src/http.c"},
                "region": {"startLine": 10, "endLine": 20}
              }
            }
          ],
          "properties": {
            "functionName": "handle_request"
          }
        }
      ]
    }
  ]
}`
	if err := os.WriteFile(oldSARIF, []byte(oldSARIFText), 0644); err != nil {
		t.Fatal(err)
	}
	oldExplorer := `{
  "resultIdToNotes": {
    "0|0": {
      "status": 1,
      "comment": "test4tool"
    }
  },
  "hiddenRules": []
}`
	if err := os.WriteFile(oldSARIF+".sarifexplorer", []byte(oldExplorer), 0644); err != nil {
		t.Fatal(err)
	}

	artifacts, err := WriteReportsWithOptions(outputDir, Options{InheritSARIFPath: oldSARIF})
	if err != nil {
		t.Fatal(err)
	}

	explorerData, err := os.ReadFile(artifacts.SARIFExplorerPath)
	if err != nil {
		t.Fatal(err)
	}
	var explorer map[string]any
	if err := json.Unmarshal(explorerData, &explorer); err != nil {
		t.Fatal(err)
	}
	notes := explorer["resultIdToNotes"].(map[string]any)
	if _, ok := notes["0|0"]; ok {
		t.Fatalf("review note stayed on old index: %s", string(explorerData))
	}
	inherited := notes["0|1"].(map[string]any)
	if inherited["status"].(float64) != 1 || inherited["comment"].(string) != "test4tool" {
		t.Fatalf("inherited note = %#v", inherited)
	}

	sarifData, err := os.ReadFile(artifacts.SARIFPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(sarifData), `"partialFingerprints"`) {
		t.Fatalf("sarif missing stable fingerprints:\n%s", string(sarifData))
	}
}

func testFindingDataFlows() []models.FindingDataFlow {
	return []models.FindingDataFlow{
		{
			Message: "request path flows into fopen",
			Steps: []models.FindingDataFlowStep{
				{
					Role:       "source",
					Message:    "request path is read from HTTP input",
					FilePath:   "src/http.c",
					LineStart:  10,
					LineEnd:    12,
					Importance: "essential",
				},
				{
					Role:       "sink",
					Message:    "path reaches fopen",
					FilePath:   "src/http.c",
					LineStart:  18,
					LineEnd:    20,
					Importance: "essential",
				},
			},
		},
	}
}
