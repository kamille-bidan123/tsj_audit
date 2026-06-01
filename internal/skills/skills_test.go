package skills

import (
	"path/filepath"
	"testing"
)

func TestLoadSkillParsesFrontmatterAndBody(t *testing.T) {
	skill, err := Load(filepath.Join("..", "..", "skills", "attack_surface", "civetweb_audit", "SKILL.md"))
	if err != nil {
		t.Fatal(err)
	}

	if skill.Name != "civetweb_audit" {
		t.Fatalf("Name = %q", skill.Name)
	}
	if skill.Description == "" {
		t.Fatal("expected description")
	}
	if !contains(skill.RequiredAuditTypes, "command_injection") {
		t.Fatalf("RequiredAuditTypes = %#v", skill.RequiredAuditTypes)
	}
	if !contains(skill.RequiredAuditTypes, "path_traversal") {
		t.Fatalf("RequiredAuditTypes = %#v", skill.RequiredAuditTypes)
	}
	if skill.Body == "" {
		t.Fatal("expected body")
	}
	if skill.Path == "" {
		t.Fatal("expected path")
	}
}

func contains(values []string, needle string) bool {
	for _, value := range values {
		if value == needle {
			return true
		}
	}
	return false
}
