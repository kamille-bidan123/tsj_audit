package export

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/models"
)

type Artifacts struct {
	JSONPath                string
	MarkdownPath            string
	HTMLPath                string
	SARIFPath               string
	IssuesSARIF             string
	SARIFExplorerPath       string
	IssuesSARIFExplorerPath string
}

type Options struct {
	InheritSARIFPath string
}

func WriteReports(outputDir string) (Artifacts, error) {
	return WriteReportsWithOptions(outputDir, Options{})
}

func WriteReportsWithOptions(outputDir string, options Options) (Artifacts, error) {
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
	artifacts.SARIFExplorerPath = artifacts.SARIFPath + ".sarifexplorer"
	artifacts.IssuesSARIFExplorerPath = artifacts.IssuesSARIF + ".sarifexplorer"
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
	sarifDoc := renderSARIF(results, false)
	if err := inheritSARIFExplorerNotes(sarifDoc, artifacts.SARIFExplorerPath, options.InheritSARIFPath); err != nil {
		return Artifacts{}, err
	}
	sarifData, err := json.MarshalIndent(sarifDoc, "", "  ")
	if err != nil {
		return Artifacts{}, err
	}
	if err := os.WriteFile(artifacts.SARIFPath, sarifData, 0644); err != nil {
		return Artifacts{}, err
	}
	issuesDoc := renderSARIF(results, true)
	if err := inheritSARIFExplorerNotes(issuesDoc, artifacts.IssuesSARIFExplorerPath, options.InheritSARIFPath); err != nil {
		return Artifacts{}, err
	}
	issuesData, err := json.MarshalIndent(issuesDoc, "", "  ")
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

func auditFindings(result models.TraceResult) []models.AuditResult {
	if len(result.AuditOutputs) == 0 {
		return result.LegacyAuditResults
	}
	var findings []models.AuditResult
	for _, stage := range result.AuditOutputs {
		findings = append(findings, flattenAuditOutput(stage.VulnerabilityType, stage.Output)...)
	}
	return findings
}

func flattenAuditOutput(auditType string, output models.AuditOutput) []models.AuditResult {
	if len(output.Findings) > 0 {
		results := make([]models.AuditResult, 0, len(output.Findings))
		for index, finding := range output.Findings {
			findingID := finding.FindingID
			if findingID == nil || *findingID == "" {
				value := fmt.Sprintf("%s-%d", auditType, index+1)
				findingID = &value
			}
			title := finding.Title
			if title == "" {
				title = fmt.Sprintf("%s finding %d", auditType, index+1)
			}
			description := finding.Description
			if description == "" {
				description = title
			}
			results = append(results, models.AuditResult{
				VulnerabilityType: auditType,
				FindingID:         findingID,
				Title:             &title,
				Severity:          finding.Severity,
				IsVulnerable:      finding.IsVulnerable,
				Confidence:        finding.Confidence,
				Description:       description,
				Recommendation:    finding.Recommendation,
				PrimaryLocation:   finding.PrimaryLocation,
				DataFlows:         finding.DataFlows,
			})
		}
		return results
	}
	description := output.Description
	if description == "" {
		description = output.Summary
	}
	if description == "" && output.Confidence == "" {
		return nil
	}
	return []models.AuditResult{
		{
			VulnerabilityType: auditType,
			IsVulnerable:      output.IsVulnerable,
			Confidence:        output.Confidence,
			Description:       description,
			Recommendation:    output.Recommendation,
		},
	}
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
		findings := auditFindings(result)
		if len(findings) == 0 {
			builder.WriteString("No audit findings.\n\n")
			continue
		}
		builder.WriteString("### Findings\n\n")
		for _, finding := range findings {
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
			if finding.Recommendation != nil && *finding.Recommendation != "" {
				builder.WriteString(fmt.Sprintf("- Recommendation: %s\n", *finding.Recommendation))
			}
			if len(finding.DataFlows) > 0 {
				builder.WriteString("- Data flows:\n")
				for _, flow := range finding.DataFlows {
					if flow.Message != "" {
						builder.WriteString(fmt.Sprintf("  - %s\n", flow.Message))
					}
					for _, step := range flow.Steps {
						builder.WriteString(fmt.Sprintf("    - `%s:%d-%d` %s %s\n", step.FilePath, step.LineStart, step.LineEnd, step.Role, step.Message))
					}
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
		findings := auditFindings(result)
		if len(findings) == 0 {
			builder.WriteString("<p>No audit findings.</p>")
		}
		for _, finding := range findings {
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
			if finding.Recommendation != nil && *finding.Recommendation != "" {
				builder.WriteString(fmt.Sprintf("<li>Recommendation: %s</li>", escapeHTML(*finding.Recommendation)))
			}
			builder.WriteString("</ul>")
			if len(finding.DataFlows) > 0 {
				builder.WriteString("<p>Data flows:</p><ul>")
				for _, flow := range finding.DataFlows {
					if flow.Message != "" {
						builder.WriteString(fmt.Sprintf("<li>%s</li>", escapeHTML(flow.Message)))
					}
					for _, step := range flow.Steps {
						builder.WriteString(fmt.Sprintf("<li><code>%s:%d-%d</code> %s %s</li>", escapeHTML(step.FilePath), step.LineStart, step.LineEnd, escapeHTML(step.Role), escapeHTML(step.Message)))
					}
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
		for _, finding := range auditFindings(result) {
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
		for _, finding := range auditFindings(result) {
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
					"confidence":        finding.Confidence,
					"is_vulnerable":     finding.IsVulnerable,
					"functionName":      context.FunctionName,
					"vulnerabilityType": finding.VulnerabilityType,
				},
				"partialFingerprints": map[string]any{
					"tsj-audit/finding/v1": stableFindingFingerprint(ruleID, context, finding),
				},
			}
			properties := sarifResult["properties"].(map[string]any)
			if result.CodeLogic != "" {
				properties["codeLogic"] = result.CodeLogic
			}
			if finding.Recommendation != nil && *finding.Recommendation != "" {
				properties["recommendation"] = *finding.Recommendation
			}
			if finding.FindingID != nil && *finding.FindingID != "" {
				sarifResult["correlationGuid"] = *finding.FindingID
			}
			if len(finding.DataFlows) > 0 {
				sarifResult["codeFlows"] = sarifCodeFlows(finding.DataFlows)
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
	if finding.PrimaryLocation.FilePath != "" {
		return models.CodeContext{
			FunctionName: finding.PrimaryLocation.FunctionName,
			FilePath:     finding.PrimaryLocation.FilePath,
			LineStart:    finding.PrimaryLocation.LineStart,
			LineEnd:      finding.PrimaryLocation.LineEnd,
		}
	}
	if step, ok := primaryDataFlowStep(finding.DataFlows); ok {
		return models.CodeContext{
			FilePath:  step.FilePath,
			LineStart: step.LineStart,
			LineEnd:   step.LineEnd,
		}
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

func primaryDataFlowStep(flows []models.FindingDataFlow) (models.FindingDataFlowStep, bool) {
	for _, flow := range flows {
		for i := len(flow.Steps) - 1; i >= 0; i-- {
			if flow.Steps[i].Role == "sink" && flow.Steps[i].FilePath != "" {
				return flow.Steps[i], true
			}
		}
	}
	for _, flow := range flows {
		for _, step := range flow.Steps {
			if step.FilePath != "" {
				return step, true
			}
		}
	}
	return models.FindingDataFlowStep{}, false
}

func sarifCodeFlows(flows []models.FindingDataFlow) []map[string]any {
	codeFlows := make([]map[string]any, 0, len(flows))
	for _, flow := range flows {
		locations := make([]map[string]any, 0, len(flow.Steps))
		for index, step := range flow.Steps {
			location := map[string]any{
				"executionOrder": index + 1,
				"location": map[string]any{
					"message": map[string]any{
						"text": step.Message,
					},
					"physicalLocation": map[string]any{
						"artifactLocation": map[string]any{
							"uri": step.FilePath,
						},
						"region": map[string]any{
							"startLine": step.LineStart,
							"endLine":   step.LineEnd,
						},
					},
				},
			}
			if step.Role != "" {
				location["kinds"] = []string{step.Role}
			}
			if step.Importance != "" {
				location["importance"] = step.Importance
			}
			locations = append(locations, location)
		}
		codeFlow := map[string]any{
			"threadFlows": []map[string]any{
				{
					"locations": locations,
				},
			},
		}
		if flow.Message != "" {
			codeFlow["message"] = map[string]any{"text": flow.Message}
		}
		codeFlows = append(codeFlows, codeFlow)
	}
	return codeFlows
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

type sarifExplorerFile struct {
	ResultIDToNotes map[string]map[string]any `json:"resultIdToNotes"`
	HiddenRules     []any                     `json:"hiddenRules"`
}

func inheritSARIFExplorerNotes(newSARIF map[string]any, newExplorerPath string, oldSARIFPath string) error {
	if oldSARIFPath == "" {
		return nil
	}
	oldSARIF, err := readJSONFile(oldSARIFPath)
	if err != nil {
		return err
	}
	oldExplorerPath := oldSARIFPath + ".sarifexplorer"
	oldExplorerData, err := os.ReadFile(oldExplorerPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("read SARIF Explorer notes %s: %w", oldExplorerPath, err)
	}
	var oldExplorer sarifExplorerFile
	if err := json.Unmarshal(oldExplorerData, &oldExplorer); err != nil {
		return fmt.Errorf("parse SARIF Explorer notes %s: %w", oldExplorerPath, err)
	}
	if len(oldExplorer.ResultIDToNotes) == 0 {
		return nil
	}

	oldRuns := sarifRuns(oldSARIF)
	oldNotesByKey := map[string]map[string]any{}
	for resultID, note := range oldExplorer.ResultIDToNotes {
		runIndex, resultIndex, ok := parseSARIFExplorerResultID(resultID)
		if !ok || runIndex >= len(oldRuns) {
			continue
		}
		oldResults := sarifResults(oldRuns[runIndex])
		if resultIndex >= len(oldResults) {
			continue
		}
		for _, key := range sarifResultKeys(oldResults[resultIndex]) {
			oldNotesByKey[key] = note
		}
	}
	if len(oldNotesByKey) == 0 {
		return nil
	}

	inherited := sarifExplorerFile{
		ResultIDToNotes: map[string]map[string]any{},
		HiddenRules:     oldExplorer.HiddenRules,
	}
	newRuns := sarifRuns(newSARIF)
	for runIndex, run := range newRuns {
		results := sarifResults(run)
		for resultIndex, result := range results {
			for _, key := range sarifResultKeys(result) {
				if note, ok := oldNotesByKey[key]; ok {
					inherited.ResultIDToNotes[fmt.Sprintf("%d|%d", runIndex, resultIndex)] = cloneMap(note)
					break
				}
			}
		}
	}
	if len(inherited.ResultIDToNotes) == 0 && len(inherited.HiddenRules) == 0 {
		return nil
	}
	data, err := json.MarshalIndent(inherited, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(newExplorerPath, data, 0644)
}

func readJSONFile(path string) (map[string]any, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open SARIF %s: %w", path, err)
	}
	defer file.Close()
	data, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("read SARIF %s: %w", path, err)
	}
	var value map[string]any
	if err := json.Unmarshal(data, &value); err != nil {
		return nil, fmt.Errorf("parse SARIF %s: %w", path, err)
	}
	return value, nil
}

func parseSARIFExplorerResultID(value string) (int, int, bool) {
	parts := strings.Split(value, "|")
	if len(parts) != 2 {
		return 0, 0, false
	}
	var runIndex, resultIndex int
	if _, err := fmt.Sscanf(parts[0], "%d", &runIndex); err != nil {
		return 0, 0, false
	}
	if _, err := fmt.Sscanf(parts[1], "%d", &resultIndex); err != nil {
		return 0, 0, false
	}
	if runIndex < 0 || resultIndex < 0 {
		return 0, 0, false
	}
	return runIndex, resultIndex, true
}

func sarifRuns(doc map[string]any) []map[string]any {
	switch rawRuns := doc["runs"].(type) {
	case []map[string]any:
		return rawRuns
	case []any:
		runs := make([]map[string]any, 0, len(rawRuns))
		for _, rawRun := range rawRuns {
			if run, ok := rawRun.(map[string]any); ok {
				runs = append(runs, run)
			}
		}
		return runs
	default:
		return nil
	}
}

func sarifResults(run map[string]any) []map[string]any {
	switch rawResults := run["results"].(type) {
	case []map[string]any:
		return rawResults
	case []any:
		results := make([]map[string]any, 0, len(rawResults))
		for _, rawResult := range rawResults {
			if result, ok := rawResult.(map[string]any); ok {
				results = append(results, result)
			}
		}
		return results
	default:
		return nil
	}
}

func sarifResultKeys(result map[string]any) []string {
	keys := []string{}
	if fingerprint := sarifFingerprint(result); fingerprint != "" {
		keys = append(keys, "fingerprint:"+fingerprint)
	}
	uri, startLine := sarifPrimaryLocation(result)
	parts := []string{
		stringValue(result["ruleId"]),
		uri,
		startLine,
		propertyString(result, "functionName"),
		propertyString(result, "taintFlow"),
		messageText(result),
	}
	keys = append(keys, "legacy:"+strings.Join(parts, "\x00"))
	return keys
}

func sarifFingerprint(result map[string]any) string {
	fingerprints, ok := result["partialFingerprints"].(map[string]any)
	if !ok {
		return ""
	}
	return stringValue(fingerprints["tsj-audit/finding/v1"])
}

func sarifPrimaryLocation(result map[string]any) (string, string) {
	var location map[string]any
	switch locations := result["locations"].(type) {
	case []map[string]any:
		if len(locations) == 0 {
			return "", ""
		}
		location = locations[0]
	case []any:
		if len(locations) == 0 {
			return "", ""
		}
		var ok bool
		location, ok = locations[0].(map[string]any)
		if !ok {
			return "", ""
		}
	default:
		return "", ""
	}
	physical, _ := location["physicalLocation"].(map[string]any)
	artifact, _ := physical["artifactLocation"].(map[string]any)
	region, _ := physical["region"].(map[string]any)
	return stringValue(artifact["uri"]), numberString(region["startLine"])
}

func propertyString(result map[string]any, name string) string {
	properties, ok := result["properties"].(map[string]any)
	if !ok {
		return ""
	}
	return stringValue(properties[name])
}

func messageText(result map[string]any) string {
	message, ok := result["message"].(map[string]any)
	if !ok {
		return ""
	}
	return stringValue(message["text"])
}

func stringValue(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func numberString(value any) string {
	switch typed := value.(type) {
	case int:
		return fmt.Sprintf("%d", typed)
	case int64:
		return fmt.Sprintf("%d", typed)
	case float64:
		return fmt.Sprintf("%.0f", typed)
	default:
		return ""
	}
}

func cloneMap(value map[string]any) map[string]any {
	clone := make(map[string]any, len(value))
	for key, item := range value {
		clone[key] = item
	}
	return clone
}

func stableFindingFingerprint(ruleID string, context models.CodeContext, finding models.AuditResult) string {
	flow := dataFlowFingerprintText(finding.DataFlows)
	parts := []string{
		ruleID,
		context.FilePath,
		context.FunctionName,
		fmt.Sprintf("%d", context.LineStart),
		flow,
	}
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	return fmt.Sprintf("%x", sum[:])
}

func dataFlowFingerprintText(flows []models.FindingDataFlow) string {
	if len(flows) == 0 {
		return ""
	}
	parts := make([]string, 0, len(flows))
	for _, flow := range flows {
		stepParts := make([]string, 0, len(flow.Steps)+1)
		stepParts = append(stepParts, flow.Message)
		for _, step := range flow.Steps {
			stepParts = append(stepParts, strings.Join([]string{
				step.Role,
				step.FilePath,
				fmt.Sprintf("%d", step.LineStart),
				step.Message,
			}, ":"))
		}
		parts = append(parts, strings.Join(stepParts, "->"))
	}
	return strings.Join(parts, "|")
}
