package runtime

import (
	"context"
	"encoding/json"
	"fmt"
)

type Mock struct {
	responses map[string]json.RawMessage
	calls     map[string]int
	requests  map[string][]RunJSONRequest
}

func NewMock(responses map[string]json.RawMessage) *Mock {
	if responses == nil {
		responses = map[string]json.RawMessage{}
	}
	return &Mock{responses: responses, calls: map[string]int{}, requests: map[string][]RunJSONRequest{}}
}

func (m *Mock) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	m.calls[req.StageName]++
	m.requests[req.StageName] = append(m.requests[req.StageName], req)
	raw, ok := m.responses[req.StageName]
	if !ok {
		return nil, nil, fmt.Errorf("mock runtime response not configured for stage %q", req.StageName)
	}
	messages := []Message{{Role: "assistant", Content: string(raw)}}
	return raw, messages, nil
}

func (m *Mock) Calls(stageName string) int {
	return m.calls[stageName]
}

func (m *Mock) Requests(stageName string) []RunJSONRequest {
	return append([]RunJSONRequest(nil), m.requests[stageName]...)
}
