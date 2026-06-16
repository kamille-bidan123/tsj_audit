package runtime

import (
	"context"
	"encoding/json"
	"testing"

	"tsj-audit/internal/models"
)

func TestEchoTraceMockSupportsEntryDiscovery(t *testing.T) {
	raw, _, err := NewEchoTraceMock().RunJSON(context.Background(), RunJSONRequest{
		StageName: "EntryDiscovery",
	})
	if err != nil {
		t.Fatal(err)
	}

	var output models.EntryDiscoveryOutput
	if err := json.Unmarshal(raw, &output); err != nil {
		t.Fatal(err)
	}
	if len(output.Functions) != 1 || output.Functions[0].FuncName == "" {
		t.Fatalf("entry discovery output = %#v", output)
	}
}
