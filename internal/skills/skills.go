package skills

import (
	"fmt"
	"os"
	"strings"

	"go.yaml.in/yaml/v4"
)

type Skill struct {
	Name               string   `yaml:"name"`
	Description        string   `yaml:"description"`
	RequiredAuditTypes []string `yaml:"required_audit_types"`
	Body               string   `yaml:"-"`
	Path               string   `yaml:"-"`
}

func Load(path string) (Skill, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Skill{}, err
	}
	text := string(data)
	if !strings.HasPrefix(text, "---\n") {
		return Skill{}, fmt.Errorf("skill missing frontmatter: %s", path)
	}

	rest := strings.TrimPrefix(text, "---\n")
	frontmatter, body, ok := strings.Cut(rest, "\n---")
	if !ok {
		return Skill{}, fmt.Errorf("skill frontmatter is not closed: %s", path)
	}

	var skill Skill
	if err := yaml.Unmarshal([]byte(frontmatter), &skill); err != nil {
		return Skill{}, fmt.Errorf("parse skill frontmatter %s: %w", path, err)
	}
	skill.Body = strings.TrimSpace(strings.TrimPrefix(body, "\n"))
	skill.Path = path
	if skill.Name == "" {
		return Skill{}, fmt.Errorf("skill missing name: %s", path)
	}
	return skill, nil
}
