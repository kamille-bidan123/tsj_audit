package runtime

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Command struct {
	Name       string
	ProjectDir string
	Timeout    time.Duration
}

func (c Command) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	if req.Status != nil {
		req.Status.SetRuntime(c.Name, "-")
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
	if err := process.Run(); err != nil {
		return nil, nil, fmt.Errorf("%s runtime failed: %w: %s", c.Name, err, commandErrorDetail(stdout.Bytes(), stderr.Bytes()))
	}
	raw := bytes.TrimSpace(stdout.Bytes())
	if outputPath != "" {
		if data, err := os.ReadFile(outputPath); err == nil && len(bytes.TrimSpace(data)) > 0 {
			raw = bytes.TrimSpace(data)
		}
	}
	if c.Name == "claudecode" {
		raw, err = unwrapClaudeCodeOutput(raw)
		if err != nil {
			return nil, nil, err
		}
	}
	if len(raw) == 0 {
		return nil, nil, fmt.Errorf("%s runtime returned empty output", c.Name)
	}
	return json.RawMessage(raw), []Message{{Role: "assistant", Content: string(raw)}}, nil
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
		return BuildClaudeCodeCommand(req.UserPrompt), "", "", func() {}, nil
	default:
		return nil, "", "", func() {}, fmt.Errorf("unsupported command runtime: %s", c.Name)
	}
}

func writeCodexTempFiles(schema json.RawMessage) (string, string, func(), error) {
	dir, err := os.MkdirTemp("", "tsj-audit-codex-*")
	if err != nil {
		return "", "", func() {}, err
	}
	cleanup := func() { _ = os.RemoveAll(dir) }
	schemaPath := filepath.Join(dir, "schema.json")
	outputPath := filepath.Join(dir, "output.json")
	if len(schema) == 0 {
		schema = json.RawMessage(`{"type":"object"}`)
	}
	if err := os.WriteFile(schemaPath, schema, 0644); err != nil {
		cleanup()
		return "", "", func() {}, err
	}
	return schemaPath, outputPath, cleanup, nil
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

func BuildClaudeCodeCommand(prompt string) []string {
	return []string{"claude", "-p", "--output-format", "json", prompt}
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
		return nil, fmt.Errorf("claudecode result did not contain a JSON object: %s", wrapper.Result)
	}
	return extracted, nil
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
