package schema

import (
	"encoding/json"
	"fmt"
	"reflect"
	"strconv"
	"strings"

	"tsj-audit/internal/models"
)

func Named(name string) (json.RawMessage, error) {
	switch name {
	case "entry_discovery":
		return ForType(models.EntryDiscoveryOutput{})
	case "trace":
		return ForType(models.TraceOutput{})
	case "audit":
		return ForType(models.AuditOutput{})
	case "exploit":
		return ForType(models.ExploitOutput{})
	default:
		return nil, fmt.Errorf("unknown schema: %s", name)
	}
}

func ForType(value any) (json.RawMessage, error) {
	schema := schemaForType(reflect.TypeOf(value))
	data, err := json.Marshal(schema)
	if err != nil {
		return nil, err
	}
	return json.RawMessage(data), nil
}

func schemaForType(t reflect.Type) map[string]any {
	if t.Kind() == reflect.Pointer {
		return map[string]any{
			"anyOf": []any{
				schemaForType(t.Elem()),
				map[string]any{"type": "null"},
			},
		}
	}
	switch t.Kind() {
	case reflect.Struct:
		return objectSchema(t)
	case reflect.Slice, reflect.Array:
		return map[string]any{"type": "array", "items": schemaForType(t.Elem())}
	case reflect.Bool:
		return map[string]any{"type": "boolean"}
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return map[string]any{"type": "integer"}
	default:
		return map[string]any{"type": "string"}
	}
}

func objectSchema(t reflect.Type) map[string]any {
	properties := map[string]any{}
	required := []string{}
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		if !field.IsExported() {
			continue
		}
		name := jsonFieldName(field)
		if name == "-" || name == "" {
			continue
		}
		properties[name] = applyFieldSchemaOptions(schemaForType(field.Type), field)
		required = append(required, name)
	}
	return map[string]any{
		"type":                 "object",
		"properties":           properties,
		"required":             required,
		"additionalProperties": false,
	}
}

func applyFieldSchemaOptions(schema map[string]any, field reflect.StructField) map[string]any {
	tag := field.Tag.Get("schema")
	if tag == "" {
		return schema
	}
	for _, option := range strings.Split(tag, ",") {
		key, value, ok := strings.Cut(strings.TrimSpace(option), "=")
		if !ok {
			continue
		}
		switch key {
		case "minLength":
			if length, err := strconv.Atoi(value); err == nil {
				schema["minLength"] = length
			}
		}
	}
	return schema
}

func jsonFieldName(field reflect.StructField) string {
	tag := field.Tag.Get("json")
	if tag == "" {
		return field.Name
	}
	parts := strings.Split(tag, ",")
	return parts[0]
}
