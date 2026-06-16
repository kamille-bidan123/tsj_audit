package prompt

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildUnifiedPromptIncludesRuntimeSchemaAndTask(t *testing.T) {
	schema := json.RawMessage(`{"type":"object"}`)
	got := BuildUnified(Options{
		Runtime:     "opencode",
		StageName:   "Trace",
		ProjectPath: "/tmp/project",
		System:      "system text",
		User:        "user task",
		Schema:      schema,
	})

	for _, needle := range []string{
		"## Unified System Prompt",
		"system text",
		"当前由 opencode 运行 Trace 阶段",
		"OpenCode 当前会话目录已经设置为待审计源码根目录：/tmp/project",
		"EntrySpec.file_path 是相对当前会话目录的路径",
		"不要给源码路径添加 project_path、../ 前缀或绝对路径前缀",
		"不要调用 question/AskUserQuestion/clarification 类工具",
		"## JSON Schema",
		`{"type":"object"}`,
		"## User Task",
		"user task",
	} {
		if !strings.Contains(got, needle) {
			t.Fatalf("prompt missing %q:\n%s", needle, got)
		}
	}
}

func TestBuildUnifiedPromptKeepsProjectPathGuidanceForOtherRuntimes(t *testing.T) {
	got := BuildUnified(Options{
		Runtime:     "codex",
		StageName:   "Trace",
		ProjectPath: "/tmp/project",
		System:      "system text",
		User:        "user task",
		Schema:      json.RawMessage(`{"type":"object"}`),
	})

	for _, needle := range []string{
		"待审计源码根目录：/tmp/project",
		"EntrySpec.file_path 是相对待审计源码根目录的路径",
	} {
		if !strings.Contains(got, needle) {
			t.Fatalf("prompt missing %q:\n%s", needle, got)
		}
	}
}
