package runtime

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"path/filepath"
	"strings"
	"sync"
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
	requestRetries       int
	requestTimeout       time.Duration
	eventMu              sync.Mutex
	eventSessions        map[string]*status.Status
	eventToolLogs        map[string]bool
	eventStarted         bool
}

type OpenCodeOptions struct {
	BaseURL              string
	ProviderID           string
	ModelID              string
	ProjectDir           string
	EnableEventStream    bool
	StructuredOutputMode string
	HTTPClient           *http.Client
	RequestRetries       int
	RequestTimeout       time.Duration
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
		requestRetries:       requestRetries(options.RequestRetries),
		requestTimeout:       options.RequestTimeout,
		eventSessions:        map[string]*status.Status{},
		eventToolLogs:        map[string]bool{},
	}
}

func (c *OpenCode) HealthCheck(ctx context.Context) error {
	if c.requestTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, c.requestTimeout)
		defer cancel()
	}
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
	attempts := c.requestRetries + 1
	for attempt := 1; attempt <= attempts; attempt++ {
		raw, messages, err := c.runJSONTimedAttempt(ctx, req, attempt, attempts)
		if err == nil {
			return raw, messages, nil
		}
		if !isRetryableTimeout(ctx, err) || attempt == attempts {
			return nil, nil, err
		}
		if req.Status != nil {
			req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[opencode] %s request timed out on attempt %d/%d; retrying", req.StageName, attempt, attempts))
		}
		if err := sleepBeforeRetry(ctx, attempt); err != nil {
			return nil, nil, err
		}
	}
	return nil, nil, fmt.Errorf("opencode retry loop exhausted")
}

func (c *OpenCode) runJSONTimedAttempt(ctx context.Context, req RunJSONRequest, attempt, attempts int) (json.RawMessage, []Message, error) {
	if c.requestTimeout <= 0 {
		return c.runJSONOnce(ctx, req)
	}
	if req.Status == nil {
		attemptCtx, cancel := context.WithTimeout(ctx, c.requestTimeout)
		defer cancel()
		return c.runJSONOnce(attemptCtx, req)
	}
	req.Status.StartAgentTimerForFunction(req.EntryKey, req.StageName, c.requestTimeout, attempt, attempts)
	defer req.Status.StopAgentTimerForFunction(req.EntryKey)
	attemptCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	expired := make(chan struct{})
	done := make(chan struct{})
	go func() {
		defer close(done)
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-attemptCtx.Done():
				return
			case <-ticker.C:
				if req.Status.AgentTimerRemainingForFunction(req.EntryKey) <= 0 {
					select {
					case <-expired:
					default:
						close(expired)
					}
					cancel()
					return
				}
			}
		}
	}()
	raw, messages, err := c.runJSONOnce(attemptCtx, req)
	cancel()
	select {
	case <-done:
	case <-time.After(500 * time.Millisecond):
	}
	select {
	case <-expired:
		if err != nil {
			return nil, nil, opencodeTimeoutError{message: fmt.Sprintf("opencode %s request timed out after %s active time", req.StageName, c.requestTimeout)}
		}
	default:
	}
	return raw, messages, err
}

func (c *OpenCode) runJSONOnce(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	sessionID, err := c.createSession(ctx)
	if err != nil {
		return nil, nil, err
	}
	if req.Status != nil {
		req.Status.SetRuntimeForTask(req.EntryKey, "opencode", sessionID)
		req.Status.LogForFunction(req.EntryKey, fmt.Sprintf("[opencode] created session=%s stage=%s", sessionID, req.StageName))
	}
	defer c.cleanupSession(sessionID, req.Status)
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

func requestRetries(value int) int {
	if value < 0 {
		return 0
	}
	return value
}

func isRetryableTimeout(ctx context.Context, err error) bool {
	if err == nil || ctx.Err() != nil {
		return false
	}
	var netError net.Error
	return errors.As(err, &netError) && netError.Timeout()
}

func sleepBeforeRetry(ctx context.Context, attempt int) error {
	delay := time.Duration(attempt) * 500 * time.Millisecond
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

type opencodeTimeoutError struct {
	message string
}

func (e opencodeTimeoutError) Error() string {
	return e.message
}

func (e opencodeTimeoutError) Timeout() bool {
	return true
}

func (e opencodeTimeoutError) Temporary() bool {
	return true
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
		return unwrapStructuredInputEnvelope(envelope.Info.Structured)
	}
	for _, part := range envelope.Parts {
		if part.Type == "tool" && part.Tool == "StructuredOutput" && len(part.State.Input) > 0 && string(part.State.Input) != "null" {
			return unwrapStructuredInputEnvelope(part.State.Input)
		}
	}
	return raw
}

func unwrapStructuredInputEnvelope(raw json.RawMessage) json.RawMessage {
	var object map[string]json.RawMessage
	if err := json.Unmarshal(raw, &object); err != nil {
		return raw
	}
	if len(object) != 1 {
		return raw
	}
	input, ok := object["input"]
	if !ok || len(input) == 0 || string(input) == "null" {
		return raw
	}
	return input
}

func (c *OpenCode) startPermissionPoller(ctx context.Context, sessionID string, state *status.Status) func() {
	if state == nil {
		return func() {}
	}
	pollCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	seenPermissions := map[string]bool{}
	seenQuestions := map[string]bool{}
	stopEvents := c.registerEventSession(sessionID, state)
	go func() {
		defer close(done)
		if err := c.PollPermissionsOnce(pollCtx, sessionID, state, seenPermissions); err != nil && pollCtx.Err() == nil {
			state.LogForFunction(state.FunctionKeyForSession(sessionID), "[opencode:permission] poll failed: "+err.Error())
		}
		if err := c.PollQuestionsOnce(pollCtx, sessionID, state, seenQuestions); err != nil && pollCtx.Err() == nil {
			state.LogForFunction(state.FunctionKeyForSession(sessionID), "[opencode:question] poll failed: "+err.Error())
		}
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-pollCtx.Done():
				return
			case <-ticker.C:
				if err := c.PollPermissionsOnce(pollCtx, sessionID, state, seenPermissions); err != nil && pollCtx.Err() == nil {
					state.LogForFunction(state.FunctionKeyForSession(sessionID), "[opencode:permission] poll failed: "+err.Error())
				}
				if err := c.PollQuestionsOnce(pollCtx, sessionID, state, seenQuestions); err != nil && pollCtx.Err() == nil {
					state.LogForFunction(state.FunctionKeyForSession(sessionID), "[opencode:question] poll failed: "+err.Error())
				}
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

func (c *OpenCode) registerEventSession(sessionID string, state *status.Status) func() {
	if !c.enableEventStream || state == nil || sessionID == "" {
		return func() {}
	}
	c.eventMu.Lock()
	c.eventSessions[sessionID] = state
	c.ensureEventListenerLocked()
	c.eventMu.Unlock()
	return func() {
		c.eventMu.Lock()
		delete(c.eventSessions, sessionID)
		c.clearToolLogsForSessionLocked(sessionID)
		c.eventMu.Unlock()
	}
}

func (c *OpenCode) ensureEventListenerLocked() {
	if c.eventStarted {
		return
	}
	c.eventStarted = true
	go func() {
		defer func() {
			c.eventMu.Lock()
			c.eventStarted = false
			c.eventMu.Unlock()
		}()
		eventCtx := context.Background()
		request, err := http.NewRequestWithContext(eventCtx, http.MethodGet, c.baseURL+"/event", nil)
		if err != nil {
			c.logEvent("[opencode:event] create request failed: " + err.Error())
			return
		}
		request.Header.Set("Accept", "text/event-stream")
		if directory, err := c.directoryHeaderValue(); err != nil {
			c.logEvent("[opencode:event] resolve project directory failed: " + err.Error())
			return
		} else if directory != "" {
			request.Header.Set("x-opencode-directory", directory)
		}
		response, err := c.httpClient.Do(request)
		if err != nil {
			c.logEvent("[opencode:event] connect failed: " + err.Error())
			return
		}
		defer response.Body.Close()
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			c.logEvent(fmt.Sprintf("[opencode:event] returned %d", response.StatusCode))
			return
		}
		c.logEvent("[opencode:event] listener started")
		scanner := bufio.NewScanner(response.Body)
		scanner.Buffer(make([]byte, 64*1024), 16*1024*1024)
		for scanner.Scan() {
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
			c.handleEvent(eventCtx, event)
		}
		if err := scanner.Err(); err != nil {
			c.logEvent("[opencode:event] read failed: " + err.Error())
		}
	}()
}

func (c *OpenCode) logEvent(message string) {
	c.eventMu.Lock()
	states := make([]*status.Status, 0, len(c.eventSessions))
	for _, state := range c.eventSessions {
		states = append(states, state)
	}
	c.eventMu.Unlock()
	for _, state := range states {
		state.Log(message)
	}
}

func (c *OpenCode) eventState(sessionID string) *status.Status {
	c.eventMu.Lock()
	defer c.eventMu.Unlock()
	return c.eventSessions[sessionID]
}

func (c *OpenCode) handleEvent(ctx context.Context, event map[string]any) {
	if request, ok := ParsePermissionEvent(event); ok {
		state := c.eventState(request.SessionID)
		if state == nil {
			return
		}
		go func() {
			key := state.FunctionKeyForSession(request.SessionID)
			state.LogForFunction(key, fmt.Sprintf("[opencode:permission] pending id=%s permission=%s patterns=%s", request.ID, request.Permission, strings.Join(request.Patterns, " | ")))
			reply, _ := state.AwaitPermissionReply(ctx, request)
			if err := c.ReplyPermission(ctx, request.ID, reply); err != nil && ctx.Err() == nil {
				state.LogForFunction(key, "[opencode:permission] reply failed: "+err.Error())
				return
			}
			state.LogForFunction(key, fmt.Sprintf("[opencode:permission] replied id=%s reply=%s", request.ID, reply))
		}()
		return
	}
	if request, ok := ParseQuestionEvent(event); ok {
		state := c.eventState(request.SessionID)
		if state == nil {
			return
		}
		go func() {
			_ = c.rejectQuestionRequest(ctx, state, request)
		}()
		return
	}
	c.logToolEvents(event, "")
}

func (c *OpenCode) logToolEvents(value any, sessionID string) {
	switch typed := value.(type) {
	case map[string]any:
		if id := firstString(typed["sessionID"], typed["session_id"]); id != "" {
			sessionID = id
		}
		if typed["type"] == "tool" {
			if toolState, ok := typed["state"].(map[string]any); ok {
				state := c.eventState(sessionID)
				if state == nil {
					return
				}
				tool := stringValue(typed["tool"])
				if tool == "" {
					tool = "unknown"
				}
				messageID := firstString(typed["messageID"], typed["message_id"])
				partID := firstString(typed["id"], typed["partID"], typed["part_id"])
				callID := firstString(typed["callID"], typed["call_id"], toolState["callID"], toolState["call_id"], partID)
				statusText := stringValue(toolState["status"])
				if statusText == "" {
					statusText = "unknown"
				}
				if !c.markToolLogOnce(sessionID, messageID, callID, tool, statusText) {
					return
				}
				detail := firstNonEmptyString(
					stringValue(toolState["title"]),
					stringValue(toolState["error"]),
					stringValue(toolState["output"]),
				)
				input := toolInputSummary(tool, toolState["input"])
				key := state.FunctionKeyForSession(sessionID)
				parts := []string{fmt.Sprintf("[opencode:tool] session=%s tool=%s call=%s status=%s", sessionID, tool, callID, statusText)}
				if detail != "" {
					parts = append(parts, "detail="+truncateForLog(detail, 500))
				}
				if input != "" {
					parts = append(parts, "input="+truncateForLog(input, 500))
				}
				state.LogForFunction(key, strings.Join(parts, " "))
			}
		}
		for _, item := range typed {
			c.logToolEvents(item, sessionID)
		}
	case []any:
		for _, item := range typed {
			c.logToolEvents(item, sessionID)
		}
	}
}

func (c *OpenCode) markToolLogOnce(sessionID, messageID, callID, tool, statusText string) bool {
	key := strings.Join([]string{sessionID, messageID, callID, tool, statusText}, "\x00")
	c.eventMu.Lock()
	defer c.eventMu.Unlock()
	if c.eventToolLogs == nil {
		c.eventToolLogs = map[string]bool{}
	}
	if c.eventToolLogs[key] {
		return false
	}
	c.eventToolLogs[key] = true
	return true
}

func (c *OpenCode) clearToolLogsForSessionLocked(sessionID string) {
	prefix := sessionID + "\x00"
	for key := range c.eventToolLogs {
		if strings.HasPrefix(key, prefix) {
			delete(c.eventToolLogs, key)
		}
	}
}

func toolInputSummary(tool string, value any) string {
	input, ok := value.(map[string]any)
	if !ok || len(input) == 0 {
		return ""
	}
	switch tool {
	case "read":
		return joinInputFields(input, "filePath", "path", "offset", "limit")
	case "grep":
		return joinInputFields(input, "pattern", "path", "include")
	case "glob":
		return joinInputFields(input, "pattern", "path")
	case "bash":
		return joinInputFields(input, "command", "description")
	}
	if summary := joinInputFields(input, "filePath", "path", "pattern", "query", "offset", "limit"); summary != "" {
		return summary
	}
	data, err := json.Marshal(input)
	if err != nil {
		return ""
	}
	return string(data)
}

func joinInputFields(input map[string]any, names ...string) string {
	parts := make([]string, 0, len(names))
	for _, name := range names {
		if value, ok := input[name]; ok {
			parts = append(parts, name+"="+inputValueString(value))
		}
	}
	return strings.Join(parts, " ")
}

func inputValueString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case float64:
		if typed == float64(int64(typed)) {
			return fmt.Sprintf("%d", int64(typed))
		}
		return fmt.Sprintf("%g", typed)
	case bool:
		if typed {
			return "true"
		}
		return "false"
	case nil:
		return "null"
	default:
		data, err := json.Marshal(typed)
		if err != nil {
			return fmt.Sprint(typed)
		}
		return string(data)
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
	raw, err := c.doJSON(ctx, http.MethodPost, "/session", map[string]string{
		"title": "tsj-audit " + time.Now().UTC().Format(time.RFC3339Nano),
	})
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

func (c *OpenCode) cleanupSession(sessionID string, state *status.Status) {
	cleanupCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := c.deleteSession(cleanupCtx, sessionID); err != nil && state != nil {
		state.Log("[opencode] delete session failed: " + err.Error())
	}
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
