package runtime

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
)

type Mock struct {
	mu                sync.Mutex
	responses         map[string]json.RawMessage
	responseSequences map[string][]json.RawMessage
	calls             map[string]int
	requests          map[string][]RunJSONRequest
}

func NewMock(responses map[string]json.RawMessage) *Mock {
	if responses == nil {
		responses = map[string]json.RawMessage{}
	}
	return &Mock{responses: responses, calls: map[string]int{}, requests: map[string][]RunJSONRequest{}}
}

func NewMockWithSequences(responses map[string][]json.RawMessage) *Mock {
	if responses == nil {
		responses = map[string][]json.RawMessage{}
	}
	return &Mock{responseSequences: responses, calls: map[string]int{}, requests: map[string][]RunJSONRequest{}}
}

func (m *Mock) RunJSON(ctx context.Context, req RunJSONRequest) (json.RawMessage, []Message, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	m.mu.Lock()
	m.calls[req.StageName]++
	m.requests[req.StageName] = append(m.requests[req.StageName], req)
	callIndex := m.calls[req.StageName] - 1
	raw, ok := m.responseForLocked(req.StageName, callIndex)
	m.mu.Unlock()
	if !ok {
		return nil, nil, fmt.Errorf("mock runtime response not configured for stage %q", req.StageName)
	}
	messages := []Message{{Role: "assistant", Content: string(raw)}}
	return raw, messages, nil
}

func (m *Mock) responseForLocked(stageName string, callIndex int) (json.RawMessage, bool) {
	if sequence := m.responseSequences[stageName]; len(sequence) > 0 {
		if callIndex < len(sequence) {
			return sequence[callIndex], true
		}
		return sequence[len(sequence)-1], true
	}
	raw, ok := m.responses[stageName]
	return raw, ok
}

func (m *Mock) Calls(stageName string) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.calls[stageName]
}

func (m *Mock) Requests(stageName string) []RunJSONRequest {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]RunJSONRequest(nil), m.requests[stageName]...)
}
