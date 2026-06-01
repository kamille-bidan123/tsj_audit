package runtime

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	"tsj-audit/internal/status"
)

type OpenCode struct {
	baseURL              string
	providerID           string
	modelID              string
	projectDir           string
	enableEventStream    bool
	structuredOutputMode string
	httpClient           *http.Client
}

type OpenCodeOptions struct {
	BaseURL              string
	ProviderID           string
	ModelID              string
	ProjectDir           string
	EnableEventStream    bool
	StructuredOutputMode string
	HTTPClient           *http.Client
}

func NewOpenCode(baseURL string, httpClient *http.Client) *OpenCode {
	return NewOpenCodeWithOptions(OpenCodeOptions{BaseURL: baseURL, HTTPClient: httpClient})
}

func NewOpenCodeWithOptions(options OpenCodeOptions) *OpenCode {
	httpClient := options.HTTPClient
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	mode := options.StructuredOutputMode
	if mode == "" {
		mode = "prompt"
	}
	return &OpenCode{
		baseURL:              strings.TrimRight(options.BaseURL, "/"),
		providerID:           strings.TrimSpace(options.ProviderID),
		modelID:              strings.TrimSpace(options.ModelID),
		projectDir:           strings.TrimSpace(options.ProjectDir),
		enableEventStream:    options.EnableEventStream,
		structuredOutputMode: strings.TrimSpace(mode),
		httpClient:           httpClient,
	}
}

func (c *OpenCode) HealthCheck(ctx context.Context) error {
	sessionID, err := c.createSession(ctx)
	if err != nil {
		return err
	}
	return c.deleteSession(ctx, sessionID)
}

func (c *OpenCode) StructuredOutputMode() string {
	return c.structuredOutputMode
}

func (c *OpenCode) ProbeStructuredOutput(ctx context.Context) (string, error) {
	previous := c.structuredOutputMode
	c.structuredOutputMode = "json_schema"
	raw, _, err := c.RunJSON(ctx, RunJSONRequest{
		StageName:  "structured_output_probe",
		UserPrompt: `Return {"ok": true}.`,
		Schema:     json.RawMessage(`{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}`),
	})
	if err != nil {
		c.structuredOutputMode = "prompt"
		return "prompt", err
	}
	var response struct {
		OK bool `json:"ok"`
	}
	if err := json.Unmarshal(raw, &response); err != nil {
		c.structuredOutputMode = "prompt"
		return "prompt", fmt.Errorf("opencode structured output probe returned invalid JSON: %w; raw=%s", err, truncateForLog(string(raw), 4000))
	}
	if !response.OK {
		c.structuredOutputMode = "prompt"
		return "prompt", fmt.Errorf("opencode structured output probe returned ok=false; raw=%s", truncateForLog(string(raw), 4000))
	}
	if previous == "" {
		c.structuredOutputMode = "json_schema"
	}
	return c.structuredOutputMode, nil
}

func truncateForLog(value string, limit int) string {
	if limit <= 0 || len(value) <= limit {
		return value
	}
	return value[:limit] + "...[truncated]"
}

func (c *OpenCode) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	sessionID, err := c.createSession(ctx)
	if err != nil {
		return nil, nil, err
	}
	defer c.deleteSession(ctx, sessionID)
	if req.Status != nil {
		req.Status.SetRuntime("opencode", sessionID)
	}
	stopPolling := c.startPermissionPoller(ctx, sessionID, req.Status)
	defer stopPolling()

	body := map[string]any{
		"parts": []map[string]string{
			{"type": "text", "text": req.UserPrompt},
		},
	}
	if c.providerID != "" && c.modelID != "" {
		body["model"] = map[string]string{
			"providerID": c.providerID,
			"modelID":    c.modelID,
		}
	}
	if c.structuredOutputMode == "json_schema" {
		schema := req.Schema
		if len(schema) == 0 {
			schema = json.RawMessage(`{"type":"object"}`)
		}
		var schemaValue any
		if err := json.Unmarshal(schema, &schemaValue); err != nil {
			return nil, nil, err
		}
		body["format"] = map[string]any{
			"type":   "json_schema",
			"schema": schemaValue,
		}
	}
	raw, err := c.doJSON(ctx, http.MethodPost, "/session/"+sessionID+"/message", body)
	if err != nil {
		return nil, nil, err
	}
	payload := extractOpenCodeStructuredPayload(raw)
	return payload, []Message{{Role: "assistant", Content: string(raw)}}, nil
}

func extractOpenCodeStructuredPayload(raw json.RawMessage) json.RawMessage {
	var envelope struct {
		Info struct {
			Structured json.RawMessage `json:"structured"`
		} `json:"info"`
		Parts []struct {
			Type  string `json:"type"`
			Tool  string `json:"tool"`
			State struct {
				Input json.RawMessage `json:"input"`
			} `json:"state"`
		} `json:"parts"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return raw
	}
	if len(envelope.Info.Structured) > 0 && string(envelope.Info.Structured) != "null" {
		return envelope.Info.Structured
	}
	for _, part := range envelope.Parts {
		if part.Type == "tool" && part.Tool == "StructuredOutput" && len(part.State.Input) > 0 && string(part.State.Input) != "null" {
			return part.State.Input
		}
	}
	return raw
}

func (c *OpenCode) startPermissionPoller(ctx context.Context, sessionID string, state *status.Status) func() {
	if state == nil {
		return func() {}
	}
	pollCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	seen := map[string]bool{}
	stopEvents := c.startEventListener(pollCtx, sessionID, state)
	go func() {
		defer close(done)
		_ = c.PollPermissionsOnce(pollCtx, sessionID, state, seen)
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-pollCtx.Done():
				return
			case <-ticker.C:
				_ = c.PollPermissionsOnce(pollCtx, sessionID, state, seen)
			}
		}
	}()
	return func() {
		cancel()
		stopEvents()
		select {
		case <-done:
		case <-time.After(500 * time.Millisecond):
		}
	}
}

func (c *OpenCode) startEventListener(ctx context.Context, sessionID string, state *status.Status) func() {
	if !c.enableEventStream {
		return func() {}
	}
	eventCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		request, err := http.NewRequestWithContext(eventCtx, http.MethodGet, c.baseURL+"/event", nil)
		if err != nil {
			state.Log("[opencode:event] create request failed: " + err.Error())
			return
		}
		request.Header.Set("Accept", "text/event-stream")
		if directory, err := c.directoryHeaderValue(); err != nil {
			state.Log("[opencode:event] resolve project directory failed: " + err.Error())
			return
		} else if directory != "" {
			request.Header.Set("x-opencode-directory", directory)
		}
		response, err := c.httpClient.Do(request)
		if err != nil {
			if eventCtx.Err() == nil {
				state.Log("[opencode:event] connect failed: " + err.Error())
			}
			return
		}
		defer response.Body.Close()
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			state.Log(fmt.Sprintf("[opencode:event] returned %d", response.StatusCode))
			return
		}
		state.Log("[opencode:event] listener started")
		scanner := bufio.NewScanner(response.Body)
		for scanner.Scan() {
			if eventCtx.Err() != nil {
				return
			}
			line := strings.TrimSpace(scanner.Text())
			if !strings.HasPrefix(line, "data:") {
				continue
			}
			payload := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			if payload == "" {
				continue
			}
			var event map[string]any
			if err := json.Unmarshal([]byte(payload), &event); err != nil {
				continue
			}
			c.handleEvent(eventCtx, sessionID, state, event)
		}
		if err := scanner.Err(); err != nil && eventCtx.Err() == nil {
			state.Log("[opencode:event] read failed: " + err.Error())
		}
	}()
	return func() {
		cancel()
		select {
		case <-done:
		case <-time.After(500 * time.Millisecond):
		}
	}
}

func (c *OpenCode) handleEvent(ctx context.Context, sessionID string, state *status.Status, event map[string]any) {
	if request, ok := ParsePermissionEvent(event); ok && request.SessionID == sessionID {
		reply, _ := state.AwaitPermissionReply(ctx, request)
		if err := c.ReplyPermission(ctx, request.ID, reply); err != nil && ctx.Err() == nil {
			state.Log("[opencode:permission] reply failed: " + err.Error())
		}
		return
	}
	logToolEvents(event, sessionID, state)
}

func logToolEvents(value any, sessionID string, state *status.Status) {
	switch typed := value.(type) {
	case map[string]any:
		if typed["type"] == "tool" {
			if toolState, ok := typed["state"].(map[string]any); ok {
				tool := stringValue(typed["tool"])
				if tool == "" {
					tool = "unknown"
				}
				callID := stringValue(toolState["callID"])
				if callID == "" {
					callID = stringValue(toolState["call_id"])
				}
				statusText := stringValue(toolState["status"])
				if statusText == "" {
					statusText = "unknown"
				}
				detail := firstNonEmptyString(
					stringValue(toolState["title"]),
					stringValue(toolState["error"]),
					stringValue(toolState["output"]),
				)
				if detail != "" {
					state.Log(fmt.Sprintf("[opencode:tool] session=%s tool=%s call=%s status=%s detail=%s", sessionID, tool, callID, statusText, truncateForLog(detail, 500)))
				} else {
					state.Log(fmt.Sprintf("[opencode:tool] session=%s tool=%s call=%s status=%s", sessionID, tool, callID, statusText))
				}
			}
		}
		for _, item := range typed {
			logToolEvents(item, sessionID, state)
		}
	case []any:
		for _, item := range typed {
			logToolEvents(item, sessionID, state)
		}
	}
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func (c *OpenCode) createSession(ctx context.Context) (string, error) {
	raw, err := c.doJSON(ctx, http.MethodPost, "/session", nil)
	if err != nil {
		return "", err
	}
	var response struct {
		ID   string `json:"id"`
		Data struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.Unmarshal(raw, &response); err != nil {
		return "", err
	}
	if response.ID != "" {
		return response.ID, nil
	}
	if response.Data.ID != "" {
		return response.Data.ID, nil
	}
	return "", fmt.Errorf("opencode session response did not include session id: %s", string(raw))
}

func (c *OpenCode) deleteSession(ctx context.Context, sessionID string) error {
	_, err := c.doJSON(ctx, http.MethodDelete, "/session/"+sessionID, nil)
	return err
}

func (c *OpenCode) doJSON(ctx context.Context, method, path string, body any) (json.RawMessage, error) {
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = bytes.NewReader(data)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return nil, err
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if directory, err := c.directoryHeaderValue(); err != nil {
		return nil, err
	} else if directory != "" {
		request.Header.Set("x-opencode-directory", directory)
	}
	response, err := c.httpClient.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()

	data, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf("opencode %s %s returned %d: %s", method, path, response.StatusCode, string(data))
	}
	return json.RawMessage(data), nil
}

func (c *OpenCode) directoryHeaderValue() (string, error) {
	if c.projectDir == "" {
		return "", nil
	}
	directory, err := filepath.Abs(c.projectDir)
	if err != nil {
		return "", err
	}
	return url.PathEscape(directory), nil
}
