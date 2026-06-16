package runtime

import (
	"context"
	"encoding/json"

	"tsj-audit/internal/status"
)

type RunJSONRequest struct {
	StageName    string
	EntryKey     string
	FunctionName string
	SystemPrompt string
	UserPrompt   string
	Schema       json.RawMessage
	Status       *status.Status
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type Client interface {
	RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error)
}

type HealthChecker interface {
	HealthCheck(ctx context.Context) error
}
