package runtime

import (
	"context"
	"encoding/json"
	"fmt"

	"tsj-audit/internal/status"
)

func (c *OpenCode) ReplyPermission(ctx context.Context, permissionID string, reply string) error {
	if permissionID == "" {
		return fmt.Errorf("permission id is required")
	}
	_, err := c.doJSON(ctx, "POST", "/permission/"+permissionID+"/reply", map[string]string{
		"response": reply,
	})
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
		seen[request.ID] = true
		reply, _ := state.AwaitPermissionReply(ctx, request)
		if err := c.ReplyPermission(ctx, request.ID, reply); err != nil {
			return err
		}
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
