package runtime

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Command struct {
	Name           string
	ProjectDir     string
	Timeout        time.Duration
	RequestRetries int
}

func (c Command) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	attempts := c.RequestRetries + 1
	if attempts < 1 {
		attempts = 1
	}
	for attempt := 1; attempt <= attempts; attempt++ {
		raw, messages, err := c.runJSONAttempt(ctx, req, attempt, attempts)
		if err == nil {
			return raw, messages, nil
		}
		if !isRetryableCommandRuntimeError(err) || attempt == attempts {
			return nil, nil, err
		}
		if req.Status != nil {
			req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[%s] %s returned malformed JSON on attempt %d/%d; retrying: %v", c.Name, req.StageName, attempt, attempts, err))
		}
		if err := sleepBeforeCommandRetry(ctx, attempt); err != nil {
			return nil, nil, err
		}
	}
	return nil, nil, fmt.Errorf("%s retry loop exhausted", c.Name)
}

func (c Command) runJSONAttempt(ctx context.Context, req RunJSONRequest, attempt, attempts int) (json.RawMessage, []Message, error) {
	if req.Status != nil {
		req.Status.SetRuntimeForTask(req.EntryKey, c.Name, "-")
	}
	command, input, outputPath, cleanup, err := c.build(req)
	if err != nil {
		return nil, nil, err
	}
	defer cleanup()

	timeout := c.Timeout
	if timeout == 0 {
		timeout = 30 * time.Minute
	}
	if req.Status != nil {
		req.Status.StartAgentTimerForFunction(req.EntryKey, req.StageName, timeout, attempt, attempts)
		defer req.Status.StopAgentTimerForFunction(req.EntryKey)
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	process := exec.CommandContext(ctx, command[0], command[1:]...)
	if c.ProjectDir != "" {
		process.Dir = c.ProjectDir
	}
	if input != "" {
		process.Stdin = bytes.NewBufferString(input)
	}
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	process.Stdout = &stdout
	process.Stderr = &stderr
	started := time.Now()
	if req.Status != nil {
		req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[%s] starting command stage=%s dir=%s", c.Name, req.StageName, commandDir(c.ProjectDir)))
	}
	if err := process.Run(); err != nil {
		if req.Status != nil {
			req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[%s] command failed after %s: %s", c.Name, time.Since(started).Round(time.Millisecond), commandErrorDetail(stdout.Bytes(), stderr.Bytes())))
		}
		return nil, nil, fmt.Errorf("%s runtime failed: %w: %s", c.Name, err, commandErrorDetail(stdout.Bytes(), stderr.Bytes()))
	}
	raw := bytes.TrimSpace(stdout.Bytes())
	if outputPath != "" {
		if data, err := os.ReadFile(outputPath); err == nil && len(bytes.TrimSpace(data)) > 0 {
			raw = bytes.TrimSpace(data)
		}
	}
	rawBeforeUnwrap := append([]byte(nil), raw...)
	if c.Name == "claudecode" {
		raw, err = unwrapClaudeCodeOutput(raw)
		if err != nil {
			return nil, nil, err
		}
	}
	if len(raw) == 0 {
		return nil, nil, fmt.Errorf("%s runtime returned empty output: %w", c.Name, errCommandEmptyOutput)
	}
	if req.Status != nil {
		req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[%s] completed command stage=%s duration=%s stdout_bytes=%d stderr_bytes=%d", c.Name, req.StageName, time.Since(started).Round(time.Millisecond), len(stdout.Bytes()), len(stderr.Bytes())))
		if trimmed := strings.TrimSpace(stderr.String()); trimmed != "" {
			req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[%s] stderr: %s", c.Name, truncateCommandLog(trimmed, 2000)))
		}
	}
	messages := commandMessages(c.Name, raw, rawBeforeUnwrap)
	return json.RawMessage(raw), messages, nil
}

func (c Command) build(req RunJSONRequest) ([]string, string, string, func(), error) {
	switch c.Name {
	case "codex":
		schemaPath, outputPath, cleanup, err := writeCodexTempFiles(req.Schema)
		if err != nil {
			return nil, "", "", func() {}, err
		}
		return BuildCodexCommand(req.StageName, schemaPath, outputPath), req.UserPrompt, outputPath, cleanup, nil
	case "claudecode":
		schemaPath, cleanup, err := writeCommandSchemaTempFile(req.Schema, "tsj-audit-claude-*")
		if err != nil {
			return nil, "", "", func() {}, err
		}
		schemaData, err := os.ReadFile(schemaPath)
		if err != nil {
			cleanup()
			return nil, "", "", func() {}, err
		}
		return BuildClaudeCodeCommand(req.UserPrompt, string(schemaData)), "", "", cleanup, nil
	default:
		return nil, "", "", func() {}, fmt.Errorf("unsupported command runtime: %s", c.Name)
	}
}

func writeCodexTempFiles(schema json.RawMessage) (string, string, func(), error) {
	schemaPath, cleanup, err := writeCommandSchemaTempFile(schema, "tsj-audit-codex-*")
	if err != nil {
		return "", "", func() {}, err
	}
	dir := filepath.Dir(schemaPath)
	outputPath := filepath.Join(dir, "output.json")
	return schemaPath, outputPath, cleanup, nil
}

func writeCommandSchemaTempFile(schema json.RawMessage, pattern string) (string, func(), error) {
	dir, err := os.MkdirTemp("", pattern)
	if err != nil {
		return "", func() {}, err
	}
	cleanup := func() { _ = os.RemoveAll(dir) }
	schemaPath := filepath.Join(dir, "schema.json")
	if len(schema) == 0 {
		schema = json.RawMessage(`{"type":"object"}`)
	}
	if err := os.WriteFile(schemaPath, schema, 0644); err != nil {
		cleanup()
		return "", func() {}, err
	}
	return schemaPath, cleanup, nil
}

func BuildCodexCommand(stageName, schemaPath, outputPath string) []string {
	sandbox := "read-only"
	if stageName == "Exploit" || stageName == "exploit" {
		sandbox = "workspace-write"
	}
	return []string{
		"codex", "exec",
		"-c", `approval_policy="never"`,
		"--skip-git-repo-check",
		"--sandbox", sandbox,
		"--color", "never",
		"--output-last-message", outputPath,
		"--output-schema", schemaPath,
		"-",
	}
}

func BuildClaudeCodeCommand(prompt string, schema string) []string {
	if strings.TrimSpace(schema) == "" {
		schema = `{"type":"object"}`
	}
	return []string{"claude", "-p", "--output-format", "json", "--json-schema", schema, "--permission-mode", "plan", prompt}
}

func commandErrorDetail(stdout []byte, stderr []byte) string {
	var parts []string
	if trimmed := strings.TrimSpace(string(stderr)); trimmed != "" {
		parts = append(parts, "stderr: "+trimmed)
	}
	if trimmed := strings.TrimSpace(string(stdout)); trimmed != "" {
		parts = append(parts, "stdout: "+trimmed)
	}
	if len(parts) == 0 {
		return "no output"
	}
	return strings.Join(parts, "\n")
}

func commandDir(projectDir string) string {
	if projectDir == "" {
		return "."
	}
	return projectDir
}

func commandMessages(runtimeName string, raw json.RawMessage, rawBeforeUnwrap []byte) []Message {
	messages := []Message{{Role: "assistant", Content: string(raw)}}
	if runtimeName == "claudecode" && len(bytes.TrimSpace(rawBeforeUnwrap)) > 0 && !bytes.Equal(bytes.TrimSpace(rawBeforeUnwrap), bytes.TrimSpace(raw)) {
		messages = append(messages, Message{Role: "assistant_raw", Content: string(bytes.TrimSpace(rawBeforeUnwrap))})
	}
	return messages
}

func truncateCommandLog(value string, limit int) string {
	if limit <= 0 || len(value) <= limit {
		return value
	}
	return value[:limit] + "...[truncated]"
}

var (
	errCommandEmptyOutput     = errors.New("command runtime returned empty output")
	errClaudeCodeNoJSONObject = errors.New("claudecode result did not contain a JSON object")
)

func unwrapClaudeCodeOutput(raw []byte) (json.RawMessage, error) {
	if len(bytes.TrimSpace(raw)) == 0 {
		return nil, nil
	}
	var wrapper struct {
		IsError bool   `json:"is_error"`
		Result  string `json:"result"`
	}
	if err := json.Unmarshal(raw, &wrapper); err != nil || wrapper.Result == "" {
		return json.RawMessage(raw), nil
	}
	if wrapper.IsError {
		return nil, fmt.Errorf("claudecode runtime returned error: %s", wrapper.Result)
	}
	extracted, ok := extractJSONObject(wrapper.Result)
	if !ok {
		return nil, fmt.Errorf("%w: %s", errClaudeCodeNoJSONObject, wrapper.Result)
	}
	return extracted, nil
}

func isRetryableCommandRuntimeError(err error) bool {
	return errors.Is(err, errCommandEmptyOutput) || errors.Is(err, errClaudeCodeNoJSONObject)
}

func sleepBeforeCommandRetry(ctx context.Context, attempt int) error {
	delay := time.Duration(attempt) * 250 * time.Millisecond
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func extractJSONObject(value string) (json.RawMessage, bool) {
	value = strings.TrimSpace(value)
	for start := strings.Index(value, "{"); start >= 0 && start < len(value); {
		depth := 0
		inString := false
		escaped := false
		for index := start; index < len(value); index++ {
			ch := value[index]
			if escaped {
				escaped = false
				continue
			}
			if ch == '\\' && inString {
				escaped = true
				continue
			}
			if ch == '"' {
				inString = !inString
				continue
			}
			if inString {
				continue
			}
			if ch == '{' {
				depth++
			}
			if ch == '}' {
				depth--
				if depth == 0 {
					candidate := strings.TrimSpace(value[start : index+1])
					if json.Valid([]byte(candidate)) {
						return json.RawMessage(candidate), true
					}
					break
				}
			}
		}
		next := strings.Index(value[start+1:], "{")
		if next < 0 {
			break
		}
		start = start + 1 + next
	}
	return nil, false
}
