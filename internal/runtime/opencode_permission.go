package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"tsj-audit/internal/status"
)

type QuestionRequest struct {
	ID        string           `json:"id"`
	SessionID string           `json:"sessionID"`
	Questions []map[string]any `json:"questions"`
}

func (c *OpenCode) ReplyPermission(ctx context.Context, permissionID string, reply string) error {
	if permissionID == "" {
		return fmt.Errorf("permission id is required")
	}
	_, err := c.doJSON(ctx, "POST", "/permission/"+permissionID+"/reply", map[string]string{
		"reply": reply,
	})
	return err
}

func (c *OpenCode) RejectQuestion(ctx context.Context, requestID string) error {
	if requestID == "" {
		return fmt.Errorf("question request id is required")
	}
	_, err := c.doJSON(ctx, "POST", "/question/"+requestID+"/reject", nil)
	return err
}

func ParsePermissionEvent(event map[string]any) (status.PermissionRequest, bool) {
	if event["type"] != "permission.asked" {
		return status.PermissionRequest{}, false
	}
	properties, ok := event["properties"].(map[string]any)
	if !ok {
		return status.PermissionRequest{}, false
	}
	request := status.PermissionRequest{
		ID:         stringValue(properties["id"]),
		SessionID:  firstString(properties["sessionID"], properties["session_id"]),
		Permission: stringValue(properties["permission"]),
		Patterns:   stringSlice(properties["patterns"]),
	}
	if metadata, ok := properties["metadata"].(map[string]any); ok {
		request.Metadata = metadata
	}
	if request.ID == "" {
		return status.PermissionRequest{}, false
	}
	return request, true
}

func ParseQuestionEvent(event map[string]any) (QuestionRequest, bool) {
	if event["type"] != "question.asked" {
		return QuestionRequest{}, false
	}
	properties, ok := event["properties"].(map[string]any)
	if !ok {
		return QuestionRequest{}, false
	}
	request := QuestionRequest{
		ID:        stringValue(properties["id"]),
		SessionID: firstString(properties["sessionID"], properties["session_id"]),
		Questions: questionItems(properties["questions"]),
	}
	if request.ID == "" {
		return QuestionRequest{}, false
	}
	return request, true
}

func (c *OpenCode) PollPermissionsOnce(ctx context.Context, sessionID string, state *status.Status, seen map[string]bool) error {
	raw, err := c.doJSON(ctx, "GET", "/permission", nil)
	if err != nil {
		return err
	}
	var permissions []map[string]any
	if err := json.Unmarshal(raw, &permissions); err != nil {
		return err
	}
	for _, item := range permissions {
		request := status.PermissionRequest{
			ID:         stringValue(item["id"]),
			SessionID:  firstString(item["sessionID"], item["session_id"]),
			Permission: stringValue(item["permission"]),
			Patterns:   stringSlice(item["patterns"]),
		}
		if metadata, ok := item["metadata"].(map[string]any); ok {
			request.Metadata = metadata
		}
		if request.ID == "" || request.SessionID != sessionID || seen[request.ID] {
			continue
		}
		if state == nil {
			continue
		}
		key := state.FunctionKeyForSession(sessionID)
		state.LogForFunction(key, fmt.Sprintf("[opencode:permission] pending id=%s permission=%s patterns=%s", request.ID, request.Permission, strings.Join(request.Patterns, " | ")))
		reply, _ := state.AwaitPermissionReply(ctx, request)
		if err := c.ReplyPermission(ctx, request.ID, reply); err != nil {
			return err
		}
		state.LogForFunction(key, fmt.Sprintf("[opencode:permission] replied id=%s reply=%s", request.ID, reply))
		seen[request.ID] = true
	}
	return nil
}

func (c *OpenCode) PollQuestionsOnce(ctx context.Context, sessionID string, state *status.Status, seen map[string]bool) error {
	raw, err := c.doJSON(ctx, "GET", "/question", nil)
	if err != nil {
		return err
	}
	var questions []QuestionRequest
	if err := json.Unmarshal(raw, &questions); err != nil {
		return err
	}
	for _, request := range questions {
		if request.ID == "" || request.SessionID != sessionID || seen[request.ID] {
			continue
		}
		if err := c.rejectQuestionRequest(ctx, state, request); err != nil {
			return err
		}
		seen[request.ID] = true
	}
	return nil
}

func (c *OpenCode) rejectQuestionRequest(ctx context.Context, state *status.Status, request QuestionRequest) error {
	key := ""
	if state != nil {
		key = state.FunctionKeyForSession(request.SessionID)
		state.LogForFunction(key, fmt.Sprintf("[opencode:question] rejecting id=%s detail=%s", request.ID, truncateForLog(summarizeQuestionRequest(request), 1000)))
	}
	if err := c.RejectQuestion(ctx, request.ID); err != nil {
		if state != nil {
			state.LogForFunction(key, "[opencode:question] reject failed: "+err.Error())
		}
		return err
	}
	if state != nil {
		state.LogForFunction(key, fmt.Sprintf("[opencode:question] rejected id=%s; audit agents must continue from available code context", request.ID))
	}
	return nil
}

func firstString(values ...any) string {
	for _, value := range values {
		if text := stringValue(value); text != "" {
			return text
		}
	}
	return ""
}

func stringValue(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func stringSlice(value any) []string {
	raw, ok := value.([]any)
	if !ok {
		if values, ok := value.([]string); ok {
			return append([]string(nil), values...)
		}
		return nil
	}
	result := make([]string, 0, len(raw))
	for _, item := range raw {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}

func questionItems(value any) []map[string]any {
	raw, ok := value.([]any)
	if !ok {
		if values, ok := value.([]map[string]any); ok {
			return append([]map[string]any(nil), values...)
		}
		return nil
	}
	result := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if object, ok := item.(map[string]any); ok {
			result = append(result, object)
		}
	}
	return result
}

func summarizeQuestionRequest(request QuestionRequest) string {
	if len(request.Questions) == 0 {
		return "-"
	}
	parts := make([]string, 0, len(request.Questions))
	for _, question := range request.Questions {
		header := stringValue(question["header"])
		text := stringValue(question["question"])
		if header != "" && text != "" {
			parts = append(parts, header+": "+text)
			continue
		}
		if text != "" {
			parts = append(parts, text)
			continue
		}
		if header != "" {
			parts = append(parts, header)
		}
	}
	if len(parts) == 0 {
		return "-"
	}
	return strings.Join(parts, " | ")
}
