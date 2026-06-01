package export

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/models"
)

type Artifacts struct {
	JSONPath     string
	MarkdownPath string
	HTMLPath     string
	SARIFPath    string
	IssuesSARIF  string
}

func WriteReports(outputDir string) (Artifacts, error) {
	store := checkpoint.Store{OutputDir: outputDir}
	resultsByName, err := store.LoadAll()
	if err != nil {
		return Artifacts{}, err
	}
	results := orderedResults(resultsByName)

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return Artifacts{}, err
	}

	artifacts := Artifacts{
		JSONPath:     filepath.Join(outputDir, "audit_results.json"),
		MarkdownPath: filepath.Join(outputDir, "audit_report.md"),
		HTMLPath:     filepath.Join(outputDir, "audit_report.html"),
		SARIFPath:    filepath.Join(outputDir, "audit_report.sarif"),
		IssuesSARIF:  filepath.Join(outputDir, "audit_issues.sarif"),
	}
	jsonData, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.JSONPath, jsonData, 0644); err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.MarkdownPath, []byte(renderMarkdown(results)), 0644); err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.HTMLPath, []byte(renderHTML(results)), 0644); err != nil {
		return Artifacts{}, err
	}
	sarifData, err := json.MarshalIndent(renderSARIF(results, false), "", "  ")
	if err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.SARIFPath, sarifData, 0644); err != nil {
		return Artifacts{}, err
	}
	issuesData, err := json.MarshalIndent(renderSARIF(results, true), "", "  ")
	if err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.IssuesSARIF, issuesData, 0644); err != nil {
		return Artifacts{}, err
	}
	return artifacts, nil
}

func orderedResults(resultsByName map[string]models.TraceResult) []models.TraceResult {
	names := make([]string, 0, len(resultsByName))
	for name := range resultsByName {
		names = append(names, name)
	}
	sort.Strings(names)
	results := make([]models.TraceResult, 0, len(names))
	for _, name := range names {
		results = append(results, resultsByName[name])
	}
	return results
}

func renderMarkdown(results []models.TraceResult) string {
	var builder strings.Builder
	builder.WriteString("# TSJ Audit Report\n\n")
	builder.WriteString(fmt.Sprintf("Total functions: %d\n\n", len(results)))
	summary := summarize(results)
	builder.WriteString(fmt.Sprintf("Vulnerable findings: %d\n", summary.VulnerableFindings))
	for _, severity := range sortedSeverityKeys(summary.BySeverity) {
		builder.WriteString(fmt.Sprintf("Severity %s: %d\n", severity, summary.BySeverity[severity]))
	}
	builder.WriteString("\n")
	for _, result := range results {
		info := result.FunctionInfo
		builder.WriteString(fmt.Sprintf("## %s\n\n", info.FuncName))
		builder.WriteString(fmt.Sprintf("- File: `%s`\n", info.FilePath))
		builder.WriteString(fmt.Sprintf("- Lines: %d-%d\n", info.StartLine, info.EndLine))
		if result.CodeLogic != "" {
			builder.WriteString(fmt.Sprintf("- Code logic: %s\n", result.CodeLogic))
		}
		builder.WriteString("\n")
		if len(result.AuditResults) == 0 {
			builder.WriteString("No audit findings.\n\n")
			continue
		}
		builder.WriteString("### Findings\n\n")
		for _, finding := range result.AuditResults {
			title := finding.VulnerabilityType
			if finding.Title != nil && *finding.Title != "" {
				title += ": " + *finding.Title
			}
			builder.WriteString(fmt.Sprintf("#### %s\n\n", title))
			builder.WriteString(fmt.Sprintf("- Vulnerable: %t\n", finding.IsVulnerable))
			builder.WriteString(fmt.Sprintf("- Confidence: %s\n", finding.Confidence))
			if finding.Severity != nil && *finding.Severity != "" {
				builder.WriteString(fmt.Sprintf("- Severity: %s\n", *finding.Severity))
			}
			builder.WriteString(fmt.Sprintf("- Description: %s\n", finding.Description))
			if finding.TaintFlow != nil && *finding.TaintFlow != "" {
				builder.WriteString(fmt.Sprintf("- Taint flow: %s\n", *finding.TaintFlow))
			}
			if finding.Recommendation != nil && *finding.Recommendation != "" {
				builder.WriteString(fmt.Sprintf("- Recommendation: %s\n", *finding.Recommendation))
			}
			if len(finding.CodeMap) > 0 {
				builder.WriteString("- Code map:\n")
				for _, context := range finding.CodeMap {
					builder.WriteString(fmt.Sprintf("  - `%s:%d-%d` %s\n", context.FilePath, context.LineStart, context.LineEnd, context.FunctionName))
				}
			}
			builder.WriteString("\n")
		}
		if len(result.ExploitResult) > 0 {
			builder.WriteString("### Exploit Results\n\n")
			for _, exploit := range result.ExploitResult {
				builder.WriteString(fmt.Sprintf("#### %s\n\n", exploit.VulnerabilityType))
				builder.WriteString(fmt.Sprintf("- Success: %t\n", exploit.Success))
				builder.WriteString(fmt.Sprintf("- PoC: `%s`\n", exploit.PocCommand))
				builder.WriteString(fmt.Sprintf("- Output: %s\n", exploit.Output))
				if exploit.Error != nil && *exploit.Error != "" {
					builder.WriteString(fmt.Sprintf("- Error: %s\n", *exploit.Error))
				}
				builder.WriteString("\n")
			}
		}
	}
	return builder.String()
}

func renderHTML(results []models.TraceResult) string {
	var builder strings.Builder
	summary := summarize(results)
	builder.WriteString("<!doctype html>\n")
	builder.WriteString("<html><head><meta charset=\"utf-8\"><title>TSJ Audit Report</title>")
	builder.WriteString("<style>body{font-family:sans-serif;max-width:1100px;margin:32px auto;padding:0 16px;line-height:1.5}code{background:#f4f4f4;padding:2px 4px}section{border-top:1px solid #ddd;padding-top:16px;margin-top:16px}</style>")
	builder.WriteString("</head><body>")
	builder.WriteString("<h1>TSJ Audit Report</h1>")
	builder.WriteString(fmt.Sprintf("<p>Total functions: %d</p>", len(results)))
	builder.WriteString(fmt.Sprintf("<p>Vulnerable findings: %d</p>", summary.VulnerableFindings))
	if len(summary.BySeverity) > 0 {
		builder.WriteString("<ul>")
		for _, severity := range sortedSeverityKeys(summary.BySeverity) {
			builder.WriteString(fmt.Sprintf("<li>Severity %s: %d</li>", escapeHTML(severity), summary.BySeverity[severity]))
		}
		builder.WriteString("</ul>")
	}
	for _, result := range results {
		info := result.FunctionInfo
		builder.WriteString("<section>")
		builder.WriteString(fmt.Sprintf("<h2>%s</h2>", escapeHTML(info.FuncName)))
		builder.WriteString(fmt.Sprintf("<p>File: <code>%s</code></p>", escapeHTML(info.FilePath)))
		builder.WriteString(fmt.Sprintf("<p>Lines: %d-%d</p>", info.StartLine, info.EndLine))
		if result.CodeLogic != "" {
			builder.WriteString(fmt.Sprintf("<p>Code logic: %s</p>", escapeHTML(result.CodeLogic)))
		}
		if len(result.AuditResults) == 0 {
			builder.WriteString("<p>No audit findings.</p>")
		}
		for _, finding := range result.AuditResults {
			title := finding.VulnerabilityType
			if finding.Title != nil && *finding.Title != "" {
				title += ": " + *finding.Title
			}
			builder.WriteString(fmt.Sprintf("<h3>%s</h3>", escapeHTML(title)))
			builder.WriteString("<ul>")
			builder.WriteString(fmt.Sprintf("<li>Vulnerable: %t</li>", finding.IsVulnerable))
			builder.WriteString(fmt.Sprintf("<li>Confidence: %s</li>", escapeHTML(finding.Confidence)))
			if finding.Severity != nil && *finding.Severity != "" {
				builder.WriteString(fmt.Sprintf("<li>Severity: %s</li>", escapeHTML(*finding.Severity)))
			}
			builder.WriteString(fmt.Sprintf("<li>Description: %s</li>", escapeHTML(finding.Description)))
			if finding.TaintFlow != nil && *finding.TaintFlow != "" {
				builder.WriteString(fmt.Sprintf("<li>Taint flow: %s</li>", escapeHTML(*finding.TaintFlow)))
			}
			if finding.Recommendation != nil && *finding.Recommendation != "" {
				builder.WriteString(fmt.Sprintf("<li>Recommendation: %s</li>", escapeHTML(*finding.Recommendation)))
			}
			builder.WriteString("</ul>")
			if len(finding.CodeMap) > 0 {
				builder.WriteString("<p>Code map:</p><ul>")
				for _, context := range finding.CodeMap {
					builder.WriteString(fmt.Sprintf("<li><code>%s:%d-%d</code> %s</li>", escapeHTML(context.FilePath), context.LineStart, context.LineEnd, escapeHTML(context.FunctionName)))
				}
				builder.WriteString("</ul>")
			}
		}
		if len(result.ExploitResult) > 0 {
			builder.WriteString("<h3>Exploit Results</h3>")
			for _, exploit := range result.ExploitResult {
				builder.WriteString(fmt.Sprintf("<h4>%s</h4>", escapeHTML(exploit.VulnerabilityType)))
				builder.WriteString("<ul>")
				builder.WriteString(fmt.Sprintf("<li>Success: %t</li>", exploit.Success))
				builder.WriteString(fmt.Sprintf("<li>PoC: <code>%s</code></li>", escapeHTML(exploit.PocCommand)))
				builder.WriteString(fmt.Sprintf("<li>Output: %s</li>", escapeHTML(exploit.Output)))
				if exploit.Error != nil && *exploit.Error != "" {
					builder.WriteString(fmt.Sprintf("<li>Error: %s</li>", escapeHTML(*exploit.Error)))
				}
				builder.WriteString("</ul>")
			}
		}
		builder.WriteString("</section>")
	}
	builder.WriteString("</body></html>\n")
	return builder.String()
}

type reportSummary struct {
	VulnerableFindings int
	BySeverity         map[string]int
}

func summarize(results []models.TraceResult) reportSummary {
	summary := reportSummary{BySeverity: map[string]int{}}
	for _, result := range results {
		for _, finding := range result.AuditResults {
			if !finding.IsVulnerable {
				continue
			}
			summary.VulnerableFindings++
			if finding.Severity != nil && *finding.Severity != "" {
				summary.BySeverity[*finding.Severity]++
			}
		}
	}
	return summary
}

func sortedSeverityKeys(values map[string]int) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func escapeHTML(value string) string {
	value = strings.ReplaceAll(value, "&", "&amp;")
	value = strings.ReplaceAll(value, "<", "&lt;")
	value = strings.ReplaceAll(value, ">", "&gt;")
	value = strings.ReplaceAll(value, `"`, "&quot;")
	value = strings.ReplaceAll(value, "'", "&#39;")
	return value
}

func renderSARIF(results []models.TraceResult, issuesOnly bool) map[string]any {
	rules := map[string]map[string]any{}
	var sarifResults []map[string]any
	for _, result := range results {
		for _, finding := range result.AuditResults {
			if issuesOnly && !finding.IsVulnerable {
				continue
			}
			ruleID := finding.VulnerabilityType
			if _, ok := rules[ruleID]; !ok {
				rules[ruleID] = map[string]any{
					"id":   ruleID,
					"name": ruleID,
					"shortDescription": map[string]any{
						"text": ruleID,
					},
					"helpUri": "https://github.com/oasis-tcs/sarif-spec",
				}
			}
			context := primaryContext(result, finding)
			message := finding.Description
			if finding.Title != nil && *finding.Title != "" {
				message = *finding.Title + ": " + message
			}
			sarifResult := map[string]any{
				"ruleId": ruleID,
				"level":  sarifLevel(finding),
				"message": map[string]any{
					"text": message,
				},
				"locations": []map[string]any{
					{
						"physicalLocation": map[string]any{
							"artifactLocation": map[string]any{
								"uri": context.FilePath,
							},
							"region": map[string]any{
								"startLine": context.LineStart,
								"endLine":   context.LineEnd,
							},
						},
					},
				},
				"properties": map[string]any{
					"confidence":    finding.Confidence,
					"is_vulnerable": finding.IsVulnerable,
				},
			}
			if finding.FindingID != nil && *finding.FindingID != "" {
				sarifResult["correlationGuid"] = *finding.FindingID
			}
			if finding.TaintFlow != nil && *finding.TaintFlow != "" {
				sarifResult["codeFlows"] = []map[string]any{
					{
						"threadFlows": []map[string]any{
							{
								"locations": []map[string]any{
									{
										"location": map[string]any{
											"message": map[string]any{
												"text": *finding.TaintFlow,
											},
											"physicalLocation": map[string]any{
												"artifactLocation": map[string]any{
													"uri": context.FilePath,
												},
												"region": map[string]any{
													"startLine": context.LineStart,
													"endLine":   context.LineEnd,
												},
											},
										},
									},
								},
							},
						},
					},
				}
			}
			sarifResults = append(sarifResults, sarifResult)
		}
	}

	ruleIDs := make([]string, 0, len(rules))
	for ruleID := range rules {
		ruleIDs = append(ruleIDs, ruleID)
	}
	sort.Strings(ruleIDs)
	ruleList := make([]map[string]any, 0, len(ruleIDs))
	for _, ruleID := range ruleIDs {
		ruleList = append(ruleList, rules[ruleID])
	}

	return map[string]any{
		"$schema": "https://json.schemastore.org/sarif-2.1.0.json",
		"version": "2.1.0",
		"runs": []map[string]any{
			{
				"tool": map[string]any{
					"driver": map[string]any{
						"name":  "tsj-audit",
						"rules": ruleList,
					},
				},
				"results": sarifResults,
			},
		},
	}
}

func primaryContext(result models.TraceResult, finding models.AuditResult) models.CodeContext {
	if len(finding.CodeMap) > 0 {
		return finding.CodeMap[0]
	}
	if len(result.CodeMap) > 0 {
		return result.CodeMap[0]
	}
	return models.CodeContext{
		FunctionName: result.FunctionInfo.FuncName,
		FilePath:     result.FunctionInfo.FilePath,
		LineStart:    result.FunctionInfo.StartLine,
		LineEnd:      result.FunctionInfo.EndLine,
	}
}

func sarifLevel(finding models.AuditResult) string {
	if !finding.IsVulnerable {
		return "note"
	}
	if finding.Severity == nil {
		return "warning"
	}
	switch strings.ToLower(*finding.Severity) {
	case "critical", "high":
		return "error"
	case "medium":
		return "warning"
	default:
		return "note"
	}
}
