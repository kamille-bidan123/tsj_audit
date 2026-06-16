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
	for _, name := range []string{"finding_id", "severity", "recommendation"} {
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

func TestAuditSchemaRequiresNonEmptyDescriptions(t *testing.T) {
	raw, err := Named("audit")
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	properties := decoded["properties"].(map[string]any)
	description := properties["description"].(map[string]any)
	if description["minLength"] != float64(1) {
		t.Fatalf("description schema = %#v", description)
	}
	confidence := properties["confidence"].(map[string]any)
	if confidence["minLength"] != float64(1) {
		t.Fatalf("confidence schema = %#v", confidence)
	}
	findings := properties["findings"].(map[string]any)
	items := findings["items"].(map[string]any)
	findingProperties := items["properties"].(map[string]any)
	findingDescription := findingProperties["description"].(map[string]any)
	if findingDescription["minLength"] != float64(1) {
		t.Fatalf("finding description schema = %#v", findingDescription)
	}
}

func TestAuditSchemaUsesDataFlowFindingShape(t *testing.T) {
	raw, err := Named("audit")
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	properties := decoded["properties"].(map[string]any)
	if _, ok := properties["code_map"]; ok {
		t.Fatalf("audit root code_map should be omitted: %#v", properties["code_map"])
	}
	if _, ok := properties["taint_flow"]; ok {
		t.Fatalf("audit root taint_flow should be omitted: %#v", properties["taint_flow"])
	}
	findings := properties["findings"].(map[string]any)
	items := findings["items"].(map[string]any)
	findingProperties := items["properties"].(map[string]any)
	for _, oldName := range []string{"code_map", "taint_flow"} {
		if _, ok := findingProperties[oldName]; ok {
			t.Fatalf("finding %s should be omitted from %#v", oldName, findingProperties)
		}
	}
	if _, ok := findingProperties["primary_location"]; !ok {
		t.Fatalf("finding primary_location missing from %#v", findingProperties)
	}
	dataFlows, ok := findingProperties["data_flows"].(map[string]any)
	if !ok {
		t.Fatalf("finding data_flows missing from %#v", findingProperties)
	}
	flowItems := dataFlows["items"].(map[string]any)
	flowProperties := flowItems["properties"].(map[string]any)
	steps := flowProperties["steps"].(map[string]any)
	stepItems := steps["items"].(map[string]any)
	stepProperties := stepItems["properties"].(map[string]any)
	for _, name := range []string{"role", "message", "file_path", "line_start", "line_end", "importance"} {
		if _, ok := stepProperties[name]; !ok {
			t.Fatalf("data flow step %s missing from %#v", name, stepProperties)
		}
	}
	if _, ok := stepProperties["function_name"]; ok {
		t.Fatalf("data flow step function_name should be omitted from %#v", stepProperties)
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
