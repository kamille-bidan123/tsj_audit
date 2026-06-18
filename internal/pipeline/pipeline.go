package pipeline

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
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
	options.Status.SetFunctionLogWriter(func(entry status.FunctionLogEntry) {
		_ = options.Checkpoints.AppendFunctionLog(checkpoint.FunctionLogEntry{
			Time:         entry.Time,
			EntryKey:     entry.EntryKey,
			Stage:        entry.Stage,
			FunctionName: entry.FunctionName,
			AuditType:    entry.AuditType,
			SessionID:    entry.SessionID,
			Message:      entry.Message,
		})
	})

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

	concurrency := options.Config.FunctionConcurrency
	if concurrency <= 0 {
		concurrency = 1
	}
	if concurrency > len(entries) && len(entries) > 0 {
		concurrency = len(entries)
	}
	if concurrency <= 1 {
		for _, entry := range entries {
			if err := runFunctionPipeline(ctx, options, entry); err != nil {
				if skipFunctionAfterRuntimeRetries(options, entry, err) {
					continue
				}
				return err
			}
		}
		return nil
	}

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	jobs := make(chan models.EntrySpec)
	errCh := make(chan error, 1)
	var workers sync.WaitGroup
	for worker := 0; worker < concurrency; worker++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for entry := range jobs {
				if err := runFunctionPipeline(ctx, options, entry); err != nil {
					if skipFunctionAfterRuntimeRetries(options, entry, err) {
						continue
					}
					select {
					case errCh <- err:
						cancel()
					default:
					}
					return
				}
			}
		}()
	}
	for _, entry := range entries {
		select {
		case <-ctx.Done():
			close(jobs)
			workers.Wait()
			select {
			case err := <-errCh:
				return err
			default:
				return ctx.Err()
			}
		case jobs <- entry:
		}
	}
	close(jobs)
	workers.Wait()
	select {
	case err := <-errCh:
		return err
	default:
		return nil
	}
}

func runFunctionPipeline(ctx context.Context, options Options, entry models.EntrySpec) error {
	entryKey := entry.Key()
	if options.Config.Resume {
		if _, ok, err := options.Checkpoints.Load(entryKey); err != nil {
			return err
		} else if ok {
			options.Status.SetFunctionStatusByKey(entryKey, "skipped")
			options.Status.LogForFunction(entryKey, "resume: skipping completed function "+entryKey)
			return nil
		}
	}
	options.Status.SetTaskStage("Trace", entryKey, entry.FuncName, "-")
	options.Status.LogForFunction(entryKey, "starting trace: "+entryKey)
	userPrompt, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	traceSchema, err := schema.Named("trace")
	if err != nil {
		return err
	}
	skillPrompt := skillUsagePrompt(entry, options.Config.ProjectPath)
	raw, err := runWithHeartbeat(ctx, options.Status, "Trace", entryKey, entry.FuncName, "-", func(ctx context.Context) (json.RawMessage, error) {
		raw, _, err := runJSONWithTranscript(ctx, options.Runtime, options.Checkpoints, options.Status, runtime.RunJSONRequest{
			StageName:    "Trace",
			EntryKey:     entryKey,
			FunctionName: entry.FuncName,
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
	options.Status.LogForFunction(entryKey, "trace completed: "+entryKey)
	var result models.TraceResult
	if err := json.Unmarshal(raw, &result); err != nil {
		return err
	}
	if err := normalizeTraceResult(&result, entry); err != nil {
		return err
	}
	auditTypes, err := auditTypesForEntry(entry, options.Config.ProjectPath, options.Config.AuditTypes)
	if err != nil {
		return err
	}
	if options.Config.EnableFallbackAudit {
		auditTypes = appendMissing(auditTypes, "fallback_security")
	}
	auditOutputs, auditResults, err := runAudits(ctx, options.Runtime, options.Status, options.Checkpoints, options.Config, entryKey, auditTypes, result)
	if err != nil {
		return err
	}
	result.AuditOutputs = append(result.AuditOutputs, auditOutputs...)
	if !options.Config.DisableExploit {
		exploitResults, err := runExploits(ctx, options.Runtime, options.Status, options.Checkpoints, options.Config, entryKey, auditResults)
		if err != nil {
			return err
		}
		result.ExploitResult = append(result.ExploitResult, exploitResults...)
	}
	if err := options.Checkpoints.SaveForKey(entryKey, result); err != nil {
		return err
	}
	options.Status.SetFunctionStatusByKey(entryKey, "done")
	options.Status.LogForFunction(entryKey, "function completed: "+entryKey)
	return nil
}

func skipFunctionAfterRuntimeRetries(options Options, entry models.EntrySpec, err error) bool {
	if !runtime.IsSkippableRuntimeError(err) {
		return false
	}
	entryKey := entry.Key()
	options.Status.SetFunctionStatusByKey(entryKey, "skipped")
	options.Status.LogForFunction(entryKey, "skipping function after runtime retries exhausted: "+err.Error())
	return true
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
			Key:    entry.Key(),
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

func normalizeTraceResult(result *models.TraceResult, entry models.EntrySpec) error {
	if result.FunctionInfo.FuncName == "" {
		result.FunctionInfo.FuncName = entry.FuncName
	}
	if result.FunctionInfo.FilePath == "" {
		result.FunctionInfo.FilePath = entry.FilePath
	}
	if result.FunctionInfo.StartLine == 0 && entry.StartLine != nil {
		result.FunctionInfo.StartLine = *entry.StartLine
	}
	if result.FunctionInfo.Skill == nil && entry.Skill != nil {
		result.FunctionInfo.Skill = entry.Skill
	}
	if result.FunctionInfo.FuncName == "" {
		return fmt.Errorf("trace result missing function_info.func_name")
	}
	if result.FunctionInfo.FilePath == "" {
		return fmt.Errorf("trace result missing function_info.file_path")
	}
	return nil
}

func runWithHeartbeat(ctx context.Context, state *status.Status, stage, key, functionName, auditType string, run func(context.Context) (json.RawMessage, error)) (json.RawMessage, error) {
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
				state.SetTaskStage(stage, key, functionName, auditType)
				state.LogForFunction(key, fmt.Sprintf("waiting for %s response: %s", stage, functionName))
			}
		}
	}()
	raw, err := run(ctx)
	close(done)
	return raw, err
}

func runJSONWithTranscript(ctx context.Context, client runtime.Client, store checkpoint.Store, state *status.Status, req runtime.RunJSONRequest) (json.RawMessage, []runtime.Message, error) {
	raw, messages, runErr := client.RunJSON(ctx, req)
	entry := checkpoint.ConversationEntry{
		Time:         time.Now().UTC().Format("20060102T150405.000000000Z"),
		EntryKey:     req.EntryKey,
		StageName:    req.StageName,
		FunctionName: req.FunctionName,
		Request: checkpoint.ConversationRequest{
			UserPrompt: req.UserPrompt,
			Schema:     append(json.RawMessage(nil), req.Schema...),
		},
		Response: checkpoint.ConversationResponse{
			Raw:      conversationRaw(raw, messages),
			Payload:  append(json.RawMessage(nil), raw...),
			Messages: conversationMessages(messages),
			Metadata: map[string]interface{}{
				"message_count": len(messages),
			},
		},
	}
	if state != nil {
		snapshot := state.Snapshot()
		entry.SessionID = snapshot.SessionID
	}
	if runErr != nil {
		entry.Error = runErr.Error()
	}
	if _, err := store.SaveConversation(entry); err != nil {
		if runErr != nil {
			return raw, messages, fmt.Errorf("%w; save conversation: %v", runErr, err)
		}
		return raw, messages, err
	}
	return raw, messages, runErr
}

func conversationMessages(messages []runtime.Message) []checkpoint.ConversationMessage {
	result := make([]checkpoint.ConversationMessage, 0, len(messages))
	for _, message := range messages {
		result = append(result, checkpoint.ConversationMessage{
			Role:    message.Role,
			Content: message.Content,
		})
	}
	return result
}

func conversationRaw(raw json.RawMessage, messages []runtime.Message) json.RawMessage {
	if len(messages) > 0 && json.Valid([]byte(messages[0].Content)) {
		return json.RawMessage(messages[0].Content)
	}
	return append(json.RawMessage(nil), raw...)
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
	entries, err := runEntryDiscovery(ctx, client, cfg, state, skillPath)
	if err != nil {
		return nil, err
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

func runExploits(ctx context.Context, client runtime.Client, state *status.Status, store checkpoint.Store, cfg config.Config, entryKey string, auditResults []models.AuditResult) ([]models.ExploitResult, error) {
	var all []models.ExploitResult
	for _, finding := range auditResults {
		if !shouldExploit(finding) {
			continue
		}
		state.SetTaskStage("Exploit", entryKey, finding.Description, finding.VulnerabilityType)
		state.LogForFunction(entryKey, "starting exploit: "+finding.VulnerabilityType)
		exploitSchema, err := schema.Named("exploit")
		if err != nil {
			return nil, err
		}
		raw, err := runWithHeartbeat(ctx, state, "Exploit", entryKey, finding.Description, finding.VulnerabilityType, func(ctx context.Context) (json.RawMessage, error) {
			raw, _, err := runJSONWithTranscript(ctx, client, store, state, runtime.RunJSONRequest{
				StageName:    "Exploit:" + finding.VulnerabilityType,
				EntryKey:     entryKey,
				FunctionName: finding.Description,
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
		state.LogForFunction(entryKey, "exploit completed: "+finding.VulnerabilityType)
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

func runAudits(ctx context.Context, client runtime.Client, state *status.Status, store checkpoint.Store, cfg config.Config, entryKey string, auditTypes []string, traceResult models.TraceResult) ([]models.AuditStageOutput, []models.AuditResult, error) {
	var outputs []models.AuditStageOutput
	var all []models.AuditResult
	loadedSpecs, _ := specs.LoadDir("audit_specs")
	for _, auditType := range auditTypes {
		state.SetTaskStage("Audit", entryKey, traceResult.FunctionInfo.FuncName, auditType)
		state.LogForFunction(entryKey, "starting audit: "+traceResult.FunctionInfo.FuncName+" / "+auditType)
		auditSchema, err := schema.Named("audit")
		if err != nil {
			return nil, nil, err
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
			return nil, nil, err
		}
		auditPrompt := prompt.BuildUnified(prompt.Options{
			Runtime:     cfg.AgentRuntime,
			StageName:   "Audit",
			ProjectPath: cfg.ProjectPath,
			System:      systemPrompt + "\n\n## Common Audit Context\n```json\n" + string(contextJSON) + "\n```",
			User:        userPrompt + "\n\n请基于 system prompt 中的公共上下文、trace code_map 函数级上下文和项目源码审计，并返回结构化审计结果；trace code_map 可以复用为审计依据，但 AuditOutput.findings[] 必须以具体污点/数据流为单位，使用 primary_location 和 data_flows[].steps[] 表达 source 到 sink 的必要路径点，不要把整个函数作为 finding 或 data_flow step，不要在 finding 内输出函数级 code_map、taint_flow 或 steps[].function_name。",
			Schema:      auditSchema,
		})
		output, err := runAuditWithMalformedRetry(ctx, client, store, state, auditType, entryKey, traceResult.FunctionInfo.FuncName, auditSchema, auditPrompt)
		if err != nil {
			return nil, nil, err
		}
		outputs = append(outputs, models.AuditStageOutput{VulnerabilityType: auditType, Output: output})
		state.LogForFunction(entryKey, "audit completed: "+traceResult.FunctionInfo.FuncName+" / "+auditType)
		results, err := auditResultsFromOutput(auditType, output)
		if err != nil {
			return nil, nil, err
		}
		all = append(all, results...)
	}
	return outputs, all, nil
}

func runAuditWithMalformedRetry(ctx context.Context, client runtime.Client, store checkpoint.Store, state *status.Status, auditType, entryKey, functionName string, auditSchema json.RawMessage, auditPrompt string) (models.AuditOutput, error) {
	const maxAttempts = 3
	promptText := auditPrompt
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		raw, err := runWithHeartbeat(ctx, state, "Audit", entryKey, functionName, auditType, func(ctx context.Context) (json.RawMessage, error) {
			raw, _, err := runJSONWithTranscript(ctx, client, store, state, runtime.RunJSONRequest{
				StageName:    "Audit:" + auditType,
				EntryKey:     entryKey,
				FunctionName: functionName,
				UserPrompt:   promptText,
				Schema:       auditSchema,
				Status:       state,
			})
			return raw, err
		})
		if err != nil {
			return models.AuditOutput{}, err
		}
		var output models.AuditOutput
		if err := json.Unmarshal(raw, &output); err != nil {
			return models.AuditOutput{}, err
		}
		malformedReason := auditOutputMalformedReason(raw, output)
		if malformedReason == "" {
			return output, nil
		}
		if attempt == maxAttempts {
			message := fmt.Sprintf("audit %s %s after %d attempts", auditType, malformedReason, maxAttempts)
			state.LogForFunction(entryKey, "audit error: "+message)
			return models.AuditOutput{
				IsVulnerable: false,
				Confidence:   "error",
				Description:  message,
				Summary:      message,
				Findings:     []models.AuditFindingOutput{},
			}, nil
		}
		state.LogForFunction(entryKey, "retrying audit after malformed output: "+functionName+" / "+auditType+" / "+malformedReason)
		promptText = auditPrompt + "\n\n上一次响应不符合 AuditOutput 要求：" + malformedReason + "。请重试，并且必须返回完整 AuditOutput JSON 对象；无漏洞时也必须填写非空 confidence 和 description 或 summary；有漏洞 findings 时，每个 finding 必须填写非空 confidence，并填写 description 或 title。不要返回函数级 code_map 条目，漏洞证据必须放在 findings[].primary_location 和 findings[].data_flows[].steps[] 中。"
	}
	return models.AuditOutput{}, fmt.Errorf("audit %s retry loop exhausted", auditType)
}

func auditOutputMalformedReason(raw json.RawMessage, output models.AuditOutput) string {
	if isCodeContextOnlyAuditOutput(raw, output) {
		return "returned code context without structured vulnerability verdict"
	}
	if len(output.Findings) > 0 {
		for index, finding := range output.Findings {
			description := finding.Description
			if description == "" {
				description = finding.Title
			}
			if description == "" || finding.Confidence == "" {
				return fmt.Sprintf("finding %d returned empty description or confidence", index+1)
			}
		}
		return ""
	}
	description := output.Description
	if description == "" {
		description = output.Summary
	}
	if description == "" || output.Confidence == "" {
		return "returned empty description or confidence"
	}
	return ""
}

func isCodeContextOnlyAuditOutput(raw json.RawMessage, output models.AuditOutput) bool {
	if output.Description != "" || output.Confidence != "" || len(output.Findings) > 0 {
		return false
	}
	var context models.CodeContext
	if err := json.Unmarshal(raw, &context); err != nil {
		return false
	}
	return context.FunctionName != "" && context.FilePath != "" && context.LineStart != 0
}

func auditResultsFromOutput(auditType string, output models.AuditOutput) ([]models.AuditResult, error) {
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
			if description == "" || finding.Confidence == "" {
				return nil, fmt.Errorf("audit %s finding %d returned empty description or confidence", auditType, index+1)
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
		return results, nil
	}
	description := output.Description
	if description == "" {
		description = output.Summary
	}
	if description == "" || output.Confidence == "" {
		return nil, fmt.Errorf("audit %s returned empty description or confidence", auditType)
	}
	return []models.AuditResult{{
		VulnerabilityType: auditType,
		IsVulnerable:      output.IsVulnerable,
		Confidence:        output.Confidence,
		Description:       description,
		Recommendation:    output.Recommendation,
	}}, nil
}
