package runtime

import (
	"context"
	"encoding/json"
	"testing"
)

func TestMockRuntimeReturnsConfiguredStageResponse(t *testing.T) {
	client := NewMock(map[string]json.RawMessage{
		"Trace": json.RawMessage(`{"code_logic":"ok"}`),
	})

	raw, messages, err := client.RunJSON(context.Background(), RunJSONRequest{StageName: "Trace"})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"code_logic":"ok"}` {
		t.Fatalf("raw = %s", raw)
	}
	if len(messages) != 1 || messages[0].Role != "assistant" {
		t.Fatalf("messages = %#v", messages)
	}
}

func TestMockRuntimeErrorsForMissingStage(t *testing.T) {
	client := NewMock(nil)

	_, _, err := client.RunJSON(context.Background(), RunJSONRequest{StageName: "Trace"})
	if err == nil {
		t.Fatal("expected missing stage error")
	}
}
