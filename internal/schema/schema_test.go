package schema

import (
	"encoding/json"
	"testing"

	"tsj-audit/internal/models"
)

func TestForTypeGeneratesObjectSchema(t *testing.T) {
	raw, err := ForType(models.TraceOutput{})
	if err != nil {
		t.Fatal(err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded["type"] != "object" {
		t.Fatalf("schema = %#v", decoded)
	}
	properties := decoded["properties"].(map[string]any)
	if _, ok := properties["function_info"]; !ok {
		t.Fatalf("missing function_info in %#v", properties)
	}
	required := decoded["required"].([]any)
	if len(required) == 0 {
		t.Fatalf("missing required fields in %#v", decoded)
	}
}

func TestForTypeRepresentsPointersAsNullableRequiredFields(t *testing.T) {
	raw, err := ForType(models.AuditFindingOutput{})
	if err != nil {
		t.Fatal(err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	required := stringSet(decoded["required"].([]any))
	for _, name := range []string{"finding_id", "severity", "taint_flow", "recommendation"} {
		if !required[name] {
			t.Fatalf("%s missing from required: %#v", name, required)
		}
	}
	properties := decoded["properties"].(map[string]any)
	findingID := properties["finding_id"].(map[string]any)
	anyOf, ok := findingID["anyOf"].([]any)
	if !ok || len(anyOf) != 2 {
		t.Fatalf("finding_id should be nullable anyOf schema: %#v", findingID)
	}
}

func TestNamedSchemas(t *testing.T) {
	for _, name := range []string{"entry_discovery", "trace", "audit", "exploit"} {
		if _, err := Named(name); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
	}
}

func stringSet(values []any) map[string]bool {
	result := map[string]bool{}
	for _, value := range values {
		if text, ok := value.(string); ok {
			result[text] = true
		}
	}
	return result
}
