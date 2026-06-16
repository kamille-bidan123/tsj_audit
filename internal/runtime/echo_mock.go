package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

type EchoTraceMock struct{}

func NewEchoTraceMock() *EchoTraceMock {
	return &EchoTraceMock{}
}

func (m *EchoTraceMock) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	if strings.HasPrefix(req.StageName, "Audit:") {
		response := map[string]any{
			"is_vulnerable":  false,
			"confidence":     "low",
			"description":    "mock audit result",
			"summary":        "mock audit result",
			"recommendation": nil,
			"findings":       []any{},
		}
		raw, err := json.Marshal(response)
		if err != nil {
			return nil, nil, err
		}
		return raw, []Message{{Role: "assistant", Content: string(raw)}}, nil
	}
	if strings.HasPrefix(req.StageName, "Exploit:") {
		auditType := strings.TrimPrefix(req.StageName, "Exploit:")
		response := map[string]any{
			"success":     false,
			"poc_command": "mock poc for " + auditType,
			"summary":     "mock exploit result",
			"error":       nil,
		}
		raw, err := json.Marshal(response)
		if err != nil {
			return nil, nil, err
		}
		return raw, []Message{{Role: "assistant", Content: string(raw)}}, nil
	}
	if req.StageName == "EntryDiscovery" {
		response := map[string]any{
			"functions": []map[string]any{
				{
					"func_name":  "mock_discovered_entry",
					"file_path":  "mock/discovered.c",
					"start_line": 1,
				},
			},
		}
		raw, err := json.Marshal(response)
		if err != nil {
			return nil, nil, err
		}
		return raw, []Message{{Role: "assistant", Content: string(raw)}}, nil
	}
	if req.StageName != "Trace" {
		return nil, nil, fmt.Errorf("echo mock does not support stage %q", req.StageName)
	}
	var entry struct {
		FuncName  string `json:"func_name"`
		FilePath  string `json:"file_path"`
		StartLine *int   `json:"start_line"`
	}
	entryJSON := extractLastJSONObject(req.UserPrompt)
	if err := json.Unmarshal([]byte(entryJSON), &entry); err != nil {
		return nil, nil, err
	}
	startLine := 1
	if entry.StartLine != nil {
		startLine = *entry.StartLine
	}
	response := map[string]any{
		"function_info": map[string]any{
			"func_name":    entry.FuncName,
			"file_path":    entry.FilePath,
			"start_line":   startLine,
			"end_line":     startLine,
			"code_snippet": "",
		},
		"code_logic":      "mock trace",
		"code_map":        []any{},
		"exploit_results": []any{},
	}
	raw, err := json.Marshal(response)
	if err != nil {
		return nil, nil, err
	}
	return raw, []Message{{Role: "assistant", Content: string(raw)}}, nil
}

func extractLastJSONObject(text string) string {
	end := strings.LastIndex(text, "}")
	if end < 0 {
		return text
	}
	depth := 0
	for i := end; i >= 0; i-- {
		switch text[i] {
		case '}':
			depth++
		case '{':
			depth--
			if depth == 0 {
				return text[i : end+1]
			}
		}
	}
	return text
}
