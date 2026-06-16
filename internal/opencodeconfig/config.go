package opencodeconfig

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func Ensure(configPath string, projectPath string) (string, error) {
	if configPath == "" {
		configPath = "opencode.json"
	}
	absProjectPath, err := filepath.Abs(projectPath)
	if err != nil {
		return "", err
	}
	if !filepath.IsAbs(configPath) {
		configPath = filepath.Join(absProjectPath, configPath)
	}
	absConfigPath, err := filepath.Abs(configPath)
	if err != nil {
		return "", err
	}

	config := map[string]any{}
	if data, err := os.ReadFile(absConfigPath); err == nil && len(data) > 0 {
		if err := json.Unmarshal(data, &config); err != nil {
			return "", fmt.Errorf("parse opencode config %s: %w", absConfigPath, err)
		}
	} else if err != nil && !os.IsNotExist(err) {
		return "", err
	}

	if _, ok := config["$schema"]; !ok {
		config["$schema"] = "https://opencode.ai/config.json"
	}
	permissions := objectValue(config["permission"])
	config["permission"] = permissions

	readAllowRules := map[string]string{"*": "allow"}
	permissions["read"] = mergeRules(permissions["read"], readAllowRules)
	permissions["glob"] = mergeRules(permissions["glob"], readAllowRules)
	permissions["grep"] = mergeRules(permissions["grep"], readAllowRules)
	permissions["list"] = mergeRules(permissions["list"], readAllowRules)
	permissions["bash"] = mergeRules(permissions["bash"], map[string]string{
		"*":                               "ask",
		"pwd":                             "allow",
		"ls *":                            "allow",
		"cat *":                           "allow",
		"sed -n *":                        "allow",
		"rg *":                            "allow",
		"grep *":                          "allow",
		"find *":                          "allow",
		"head *":                          "allow",
		"tail *":                          "allow",
		"xargs *":                         "allow",
		"pkg-config *":                    "allow",
		"python scripts/scan.py *":        "allow",
		"python3 scripts/scan.py *":       "allow",
		"python scripts/scan_ioctl.py *":  "allow",
		"python3 scripts/scan_ioctl.py *": "allow",
		"python .agents/skills/*/scripts/scan.py *":         "allow",
		"python3 .agents/skills/*/scripts/scan.py *":        "allow",
		"python skills/attack_surface/*/scripts/scan.py *":  "allow",
		"python3 skills/attack_surface/*/scripts/scan.py *": "allow",
		"go run ./cmd/scan *":                               "allow",
	})
	permissions["external_directory"] = mergeRules(permissions["external_directory"], map[string]string{
		"*":                                 "allow",
		absProjectPath:                      "allow",
		filepath.Join(absProjectPath, "**"): "allow",
	})
	if _, ok := permissions["edit"]; !ok {
		permissions["edit"] = "deny"
	}
	if _, ok := permissions["question"]; !ok {
		permissions["question"] = "deny"
	}

	if err := os.MkdirAll(filepath.Dir(absConfigPath), 0755); err != nil {
		return "", err
	}
	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return "", err
	}
	data = append(data, '\n')
	if err := os.WriteFile(absConfigPath, data, 0644); err != nil {
		return "", err
	}
	return absConfigPath, nil
}

func objectValue(value any) map[string]any {
	if object, ok := value.(map[string]any); ok {
		return object
	}
	return map[string]any{}
}

func mergeRules(existing any, rules map[string]string) map[string]any {
	merged := map[string]any{}
	switch typed := existing.(type) {
	case map[string]any:
		for key, value := range typed {
			merged[key] = value
		}
	case map[string]string:
		for key, value := range typed {
			merged[key] = value
		}
	case string:
		if typed != "" {
			merged["*"] = typed
		}
	}
	for key, value := range rules {
		merged[key] = value
	}
	return merged
}
