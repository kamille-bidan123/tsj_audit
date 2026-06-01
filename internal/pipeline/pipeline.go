package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/config"
	"tsj-audit/internal/models"
	"tsj-audit/internal/prompt"
	"tsj-audit/internal/runtime"
	"tsj-audit/internal/scanner"
	"tsj-audit/internal/schema"
	"tsj-audit/internal/skills"
	"tsj-audit/internal/specs"
	"tsj-audit/internal/status"
)

type Options struct {
	Config      config.Config
	Runtime     runtime.Client
	Status      *status.Status
	Checkpoints checkpoint.Store
}

func Run(ctx context.Context, options Options) error {
	if options.Runtime == nil {
		return fmt.Errorf("runtime client is required")
	}
	if options.Status == nil {
		options.Status = status.New()
	}
	if options.Checkpoints.OutputDir == "" {
		options.Checkpoints = checkpoint.Store{OutputDir: options.Config.OutputDir}
	}

	if err := scanner.ValidateEntrySources(options.Config.Scan, options.Config.Entry, options.Config.AttackSurfaceSkill); err != nil {
		return err
	}

	var entries []models.EntrySpec
	var err error
	switch {
	case options.Config.Entry != "":
		entries, err = scanner.LoadEntrySpecs(options.Config.Entry)
	case options.Config.Scan != "":
		entries, err = scanner.RunScan(ctx, options.Config.Scan, options.Config.ProjectPath)
	case options.Config.AttackSurfaceSkill != "":
		entries, err = discoverAttackSurfaceEntries(ctx, options.Runtime, options.Config, options.Status)
	}
	if err != nil {
		return err
	}
	options.Status.SetFunctions(functionStatuses(entries))

	for _, entry := range entries {
		if options.Config.Resume {
			if _, ok, err := options.Checkpoints.Load(entry.FuncName); err != nil {
				return err
			} else if ok {
				options.Status.SetFunctionStatus(entry.FuncName, "skipped")
				options.Status.Log("resume: skipping completed function " + entry.FuncName)
				continue
			}
		}
		options.Status.SetStage("Trace", entry.FuncName, "-")
		options.Status.Log("starting trace: " + entry.FuncName)
		userPrompt, err := json.Marshal(entry)
		if err != nil {
			return err
		}
		traceSchema, err := schema.Named("trace")
		if err != nil {
			return err
		}
		skillPrompt := skillUsagePrompt(entry, options.Config.ProjectPath)
		raw, err := runWithHeartbeat(ctx, options.Status, "Trace", entry.FuncName, "-", func(ctx context.Context) (json.RawMessage, error) {
			raw, _, err := options.Runtime.RunJSON(ctx, runtime.RunJSONRequest{
				StageName: "Trace",
				UserPrompt: prompt.BuildUnified(prompt.Options{
					Runtime:     options.Config.AgentRuntime,
					StageName:   "Trace",
					ProjectPath: options.Config.ProjectPath,
					System:      "你是一个代码审计 Trace Agent，负责根据入口函数和源码补齐 FunctionInfo，并输出代码逻辑和 Code Map。\n\n" + skillPrompt,
					User:        string(userPrompt),
					Schema:      traceSchema,
				}),
				Schema: traceSchema,
				Status: options.Status,
			})
			return raw, err
		})
		if err != nil {
			return err
		}
		options.Status.Log("trace completed: " + entry.FuncName)
		var result models.TraceResult
		if err := json.Unmarshal(raw, &result); err != nil {
			return err
		}
		auditTypes, err := auditTypesForEntry(entry, options.Config.ProjectPath, options.Config.AuditTypes)
		if err != nil {
			return err
		}
		if options.Config.EnableFallbackAudit {
			auditTypes = appendMissing(auditTypes, "fallback_security")
		}
		auditResults, err := runAudits(ctx, options.Runtime, options.Status, options.Config, auditTypes, result)
		if err != nil {
			return err
		}
		result.AuditResults = append(result.AuditResults, auditResults...)
		if !options.Config.DisableExploit {
			exploitResults, err := runExploits(ctx, options.Runtime, options.Status, options.Config, auditResults)
			if err != nil {
				return err
			}
			result.ExploitResult = append(result.ExploitResult, exploitResults...)
		}
		if err := options.Checkpoints.Save(result); err != nil {
			return err
		}
		options.Status.SetFunctionStatus(entry.FuncName, "done")
		options.Status.Log("function completed: " + entry.FuncName)
	}
	return nil
}

func functionStatuses(entries []models.EntrySpec) []status.FunctionStatus {
	result := make([]status.FunctionStatus, 0, len(entries))
	for _, entry := range entries {
		skill := ""
		if entry.Skill != nil {
			skill = *entry.Skill
		}
		result = append(result, status.FunctionStatus{
			Name:   entry.FuncName,
			File:   entry.FilePath,
			Line:   intValue(entry.StartLine),
			Skill:  skill,
			Status: "pending",
		})
	}
	return result
}

func intValue(value *int) int {
	if value == nil {
		return 0
	}
	return *value
}

func runWithHeartbeat(ctx context.Context, state *status.Status, stage, functionName, auditType string, run func(context.Context) (json.RawMessage, error)) (json.RawMessage, error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-done:
				return
			case <-ticker.C:
				state.SetStage(stage, functionName, auditType)
				state.Heartbeat(fmt.Sprintf("waiting for %s response: %s", stage, functionName))
			}
		}
	}()
	raw, err := run(ctx)
	close(done)
	return raw, err
}

func appendMissing(values []string, value string) []string {
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

func discoverAttackSurfaceEntries(ctx context.Context, client runtime.Client, cfg config.Config, state *status.Status) ([]models.EntrySpec, error) {
	skillName := cfg.AttackSurfaceSkill
	skillPath, err := resolveSkillPathForProject(cfg.ProjectPath, skillName)
	if err != nil {
		return nil, err
	}
	scanPath := filepath.Join(filepath.Dir(skillPath), "scripts", "scan.py")
	var entries []models.EntrySpec
	if nativeEntries, ok, err := scanner.RunAttackSurfaceScan(skillName, cfg.ProjectPath); err != nil {
		return nil, err
	} else if ok {
		entries = nativeEntries
	} else if _, err := os.Stat(scanPath); err == nil {
		entries, err = scanner.RunScan(ctx, scanPath, cfg.ProjectPath)
		if err != nil {
			return nil, err
		}
	} else {
		entries, err = runEntryDiscovery(ctx, client, cfg, state, skillPath)
		if err != nil {
			return nil, err
		}
	}
	if cfg.OutputDir != "" {
		if err := os.MkdirAll(cfg.OutputDir, 0755); err != nil {
			return nil, err
		}
		data, err := json.MarshalIndent(entries, "", "  ")
		if err != nil {
			return nil, err
		}
		if err := os.WriteFile(filepath.Join(cfg.OutputDir, "discovered_functions.json"), data, 0644); err != nil {
			return nil, err
		}
	}
	return entries, nil
}

func runEntryDiscovery(ctx context.Context, client runtime.Client, cfg config.Config, state *status.Status, skillPath string) ([]models.EntrySpec, error) {
	entrySchema, err := schema.Named("entry_discovery")
	if err != nil {
		return nil, err
	}
	systemPrompt := "你是攻击面入口发现 Agent，负责根据指定 attack surface skill 在项目源码中发现所有审计入口函数。\n\n" +
		prompt.SkillUsage(cfg.AttackSurfaceSkill, skillPath) +
		"\n\n## Discovery Contract\n- 只输出包含 functions 字段的 JSON object。\n- 每个 EntrySpec.skill 必须设置为指定 skill。\n- 不做漏洞审计，不输出 Markdown。"
	raw, _, err := client.RunJSON(ctx, runtime.RunJSONRequest{
		StageName: "EntryDiscovery",
		UserPrompt: prompt.BuildUnified(prompt.Options{
			Runtime:     cfg.AgentRuntime,
			StageName:   "EntryDiscovery",
			ProjectPath: cfg.ProjectPath,
			System:      systemPrompt,
			User:        `请根据 attack surface skill 自动发现该攻击面的所有接口入口函数，并返回 JSON object：{"functions": EntrySpec[]}。`,
			Schema:      entrySchema,
		}),
		Schema: entrySchema,
		Status: state,
	})
	if err != nil {
		return nil, err
	}
	var output models.EntryDiscoveryOutput
	if err := json.Unmarshal(raw, &output); err != nil {
		return nil, err
	}
	for index := range output.Functions {
		output.Functions[index].Skill = &cfg.AttackSurfaceSkill
	}
	return output.Functions, nil
}

func auditTypesForEntry(entry models.EntrySpec, projectPath string, explicit []string) ([]string, error) {
	var auditTypes []string
	seen := map[string]bool{}
	add := func(values []string) {
		for _, value := range values {
			if value == "" || seen[value] {
				continue
			}
			seen[value] = true
			auditTypes = append(auditTypes, value)
		}
	}
	if entry.Skill != nil && *entry.Skill != "" {
		skillPath, err := resolveSkillPathForProject(projectPath, *entry.Skill)
		if err != nil {
			return nil, err
		}
		skill, err := skills.Load(skillPath)
		if err != nil {
			return nil, err
		}
		add(skill.RequiredAuditTypes)
	}
	add(explicit)
	return auditTypes, nil
}

func resolveSkillPath(name string) (string, error) {
	return resolveSkillPathForProject("", name)
}

func resolveSkillPathForProject(projectPath string, name string) (string, error) {
	if projectPath != "" {
		candidate := filepath.Join(projectPath, "skills", "attack_surface", name, "SKILL.md")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		candidate := filepath.Join(cwd, "skills", "attack_surface", name, "SKILL.md")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
		parent := filepath.Dir(cwd)
		if parent == cwd {
			return "", fmt.Errorf("skill not found: %s", name)
		}
		cwd = parent
	}
}

func runExploits(ctx context.Context, client runtime.Client, state *status.Status, cfg config.Config, auditResults []models.AuditResult) ([]models.ExploitResult, error) {
	var all []models.ExploitResult
	for _, finding := range auditResults {
		if !shouldExploit(finding) {
			continue
		}
		state.SetStage("Exploit", finding.Description, finding.VulnerabilityType)
		state.Log("starting exploit: " + finding.VulnerabilityType)
		exploitSchema, err := schema.Named("exploit")
		if err != nil {
			return nil, err
		}
		raw, err := runWithHeartbeat(ctx, state, "Exploit", finding.Description, finding.VulnerabilityType, func(ctx context.Context) (json.RawMessage, error) {
			raw, _, err := client.RunJSON(ctx, runtime.RunJSONRequest{
				StageName: "Exploit:" + finding.VulnerabilityType,
				UserPrompt: prompt.BuildUnified(prompt.Options{
					Runtime:     cfg.AgentRuntime,
					StageName:   "Exploit",
					ProjectPath: cfg.ProjectPath,
					System:      exploitSystemPrompt(finding, cfg.TargetBaseURL),
					User:        finding.Description,
					Schema:      exploitSchema,
				}),
				Schema: exploitSchema,
				Status: state,
			})
			return raw, err
		})
		if err != nil {
			return nil, err
		}
		state.Log("exploit completed: " + finding.VulnerabilityType)
		var output models.ExploitOutput
		if err := json.Unmarshal(raw, &output); err != nil {
			return nil, err
		}
		all = append(all, models.ExploitResult{
			VulnerabilityType: finding.VulnerabilityType,
			Success:           output.Success,
			PocCommand:        output.PocCommand,
			Output:            output.Summary,
			Error:             output.Error,
		})
	}
	return all, nil
}

func exploitSystemPrompt(finding models.AuditResult, targetBaseURL string) string {
	systemPrompt := "你是一个安全 PoC 验证 Agent，只生成安全、最小化、可复现的验证命令。"
	if targetBaseURL != "" {
		systemPrompt += "\n目标服务基础 URL：" + targetBaseURL
	}
	if len(finding.CodeMap) == 0 {
		return systemPrompt
	}
	for _, context := range finding.CodeMap {
		if context.IsEntryPoint {
			continue
		}
	}
	return systemPrompt
}

func shouldExploit(finding models.AuditResult) bool {
	if finding.VulnerabilityType == "fallback_security" {
		return false
	}
	if !finding.IsVulnerable {
		return false
	}
	switch finding.Confidence {
	case "medium", "high", "critical":
		return true
	default:
		return false
	}
}

func skillUsagePrompt(entry models.EntrySpec, projectPath string) string {
	if entry.Skill == nil || *entry.Skill == "" {
		return ""
	}
	path, err := resolveSkillPathForProject(projectPath, *entry.Skill)
	if err != nil {
		return ""
	}
	return prompt.SkillUsage(*entry.Skill, path)
}

func runAudits(ctx context.Context, client runtime.Client, state *status.Status, cfg config.Config, auditTypes []string, traceResult models.TraceResult) ([]models.AuditResult, error) {
	var all []models.AuditResult
	loadedSpecs, _ := specs.LoadDir("audit_specs")
	for _, auditType := range auditTypes {
		state.SetStage("Audit", traceResult.FunctionInfo.FuncName, auditType)
		state.Log("starting audit: " + traceResult.FunctionInfo.FuncName + " / " + auditType)
		auditSchema, err := schema.Named("audit")
		if err != nil {
			return nil, err
		}
		systemPrompt := "你是一个代码安全审计 Agent，必须基于入口函数、Code Map 和源码证据判断漏洞。"
		userPrompt := traceResult.FunctionInfo.FuncName
		if spec, ok := loadedSpecs[auditType]; ok {
			systemPrompt = spec.SystemPrompt()
			userPrompt = spec.UserPrompt
		}
		if traceResult.FunctionInfo.Skill != nil && *traceResult.FunctionInfo.Skill != "" {
			if path, err := resolveSkillPathForProject(cfg.ProjectPath, *traceResult.FunctionInfo.Skill); err == nil {
				systemPrompt += "\n\n" + prompt.SkillUsage(*traceResult.FunctionInfo.Skill, path)
			}
		}
		contextJSON, err := json.MarshalIndent(traceResult, "", "  ")
		if err != nil {
			return nil, err
		}
		raw, err := runWithHeartbeat(ctx, state, "Audit", traceResult.FunctionInfo.FuncName, auditType, func(ctx context.Context) (json.RawMessage, error) {
			raw, _, err := client.RunJSON(ctx, runtime.RunJSONRequest{
				StageName: "Audit:" + auditType,
				UserPrompt: prompt.BuildUnified(prompt.Options{
					Runtime:     cfg.AgentRuntime,
					StageName:   "Audit",
					ProjectPath: cfg.ProjectPath,
					System:      systemPrompt + "\n\n## Common Audit Context\n```json\n" + string(contextJSON) + "\n```",
					User:        userPrompt + "\n\n请基于 system prompt 中的公共上下文、code_map 和项目源码审计，并返回结构化审计结果。",
					Schema:      auditSchema,
				}),
				Schema: auditSchema,
				Status: state,
			})
			return raw, err
		})
		if err != nil {
			return nil, err
		}
		state.Log("audit completed: " + traceResult.FunctionInfo.FuncName + " / " + auditType)
		var response struct {
			Results []models.AuditResult `json:"results"`
		}
		if err := json.Unmarshal(raw, &response); err != nil {
			var output models.AuditOutput
			if err := json.Unmarshal(raw, &output); err != nil {
				return nil, err
			}
			all = append(all, auditResultsFromOutput(auditType, traceResult.CodeMap, output)...)
			continue
		}
		if len(response.Results) > 0 {
			all = append(all, response.Results...)
			continue
		}
		var output models.AuditOutput
		if err := json.Unmarshal(raw, &output); err != nil {
			return nil, err
		}
		all = append(all, auditResultsFromOutput(auditType, traceResult.CodeMap, output)...)
	}
	return all, nil
}

func auditResultsFromOutput(auditType string, fallbackCodeMap []models.CodeContext, output models.AuditOutput) []models.AuditResult {
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
			codeMap := finding.CodeMap
			if len(codeMap) == 0 {
				codeMap = fallbackCodeMap
			}
			results = append(results, models.AuditResult{
				VulnerabilityType: auditType,
				FindingID:         findingID,
				Title:             &title,
				Severity:          finding.Severity,
				IsVulnerable:      finding.IsVulnerable,
				Confidence:        finding.Confidence,
				Description:       description,
				TaintFlow:         finding.TaintFlow,
				Recommendation:    finding.Recommendation,
				CodeMap:           codeMap,
			})
		}
		return results
	}
	description := output.Description
	if description == "" {
		description = output.Summary
	}
	if description == "" {
		description = "审计未提供描述"
	}
	codeMap := output.CodeMap
	if len(codeMap) == 0 {
		codeMap = fallbackCodeMap
	}
	return []models.AuditResult{{
		VulnerabilityType: auditType,
		IsVulnerable:      output.IsVulnerable,
		Confidence:        output.Confidence,
		Description:       description,
		TaintFlow:         output.TaintFlow,
		Recommendation:    output.Recommendation,
		CodeMap:           codeMap,
	}}
}
