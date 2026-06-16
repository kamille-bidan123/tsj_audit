package config

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Config struct {
	AgentRuntime                              string   `json:"agent_runtime"`
	OpenCodeBaseURL                           string   `json:"opencode_base_url"`
	OpenCodeProviderID                        string   `json:"opencode_provider_id"`
	OpenCodeModelID                           string   `json:"opencode_model_id"`
	OpenCodeEnableEventStream                 bool     `json:"opencode_enable_event_stream"`
	OpenCodeStructuredOutputMode              string   `json:"opencode_structured_output_mode"`
	OpenCodeRequirePromptFallbackConfirmation bool     `json:"opencode_require_prompt_fallback_confirmation"`
	OpenCodeInjectProjectConfig               bool     `json:"opencode_inject_project_config"`
	OpenCodeConfigPath                        string   `json:"opencode_config_path"`
	OpenCodeRequestRetries                    int      `json:"opencode_request_retries"`
	ExternalRuntimeTimeoutSeconds             int      `json:"external_runtime_timeout_seconds"`
	FunctionConcurrency                       int      `json:"function_concurrency"`
	DisableExploit                            bool     `json:"disable_exploit"`
	EnableFallbackAudit                       bool     `json:"enable_fallback_audit"`
	AuditTypes                                []string `json:"audit_types"`
	Debug                                     bool     `json:"debug"`
	DryRun                                    bool     `json:"dry_run"`
	Resume                                    bool     `json:"resume"`
	ProjectPath                               string   `json:"project_path"`
	Scan                                      string   `json:"scan"`
	Entry                                     string   `json:"entry"`
	AttackSurfaceSkill                        string   `json:"attack_surface_skill"`
	OutputDir                                 string   `json:"output_dir"`
	TargetBaseURL                             string   `json:"target_base_url"`
}

type Args struct {
	ConfigFile                   string
	AgentRuntime                 string
	OpenCodeBaseURL              string
	OpenCodeProviderID           string
	OpenCodeModelID              string
	OpenCodeEnableEventStream    *bool
	OpenCodeStructuredOutputMode string
	DisableExploit               *bool
	EnableFallbackAudit          *bool
	Debug                        *bool
	DryRun                       *bool
	Resume                       *bool
	Scan                         string
	Entry                        string
	AttackSurfaceSkill           string
	ProjectPath                  string
	OutputDir                    string
	TargetBaseURL                string
	AuditTypes                   string
	FunctionConcurrency          int
}

func Load(args Args) (Config, error) {
	cfg := defaults()
	envPath, err := findEnvFile(args.ConfigFile)
	if err != nil {
		return Config{}, err
	}
	if envPath != "" {
		values, err := readEnvFile(envPath)
		if err != nil {
			return Config{}, err
		}
		applyEnv(&cfg, values)
	}
	applyArgs(&cfg, args)
	return cfg, nil
}

func defaults() Config {
	return Config{
		AgentRuntime:                              "codex",
		OpenCodeBaseURL:                           "http://127.0.0.1:4096",
		OpenCodeStructuredOutputMode:              "auto",
		OpenCodeRequirePromptFallbackConfirmation: true,
		OpenCodeInjectProjectConfig:               true,
		OpenCodeConfigPath:                        "opencode.json",
		OpenCodeRequestRetries:                    2,
		ExternalRuntimeTimeoutSeconds:             1800,
		FunctionConcurrency:                       1,
		ProjectPath:                               ".",
		OutputDir:                                 "output",
		TargetBaseURL:                             "http://localhost:8081",
	}
}

func findEnvFile(explicit string) (string, error) {
	if explicit != "" {
		if info, err := os.Stat(explicit); err != nil {
			return "", fmt.Errorf("specified config file does not exist: %s", explicit)
		} else if info.IsDir() {
			return "", fmt.Errorf("specified config path is not a file: %s", explicit)
		}
		return explicit, nil
	}
	if info, err := os.Stat(".env"); err == nil && !info.IsDir() {
		return ".env", nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", nil
	}
	homeEnv := filepath.Join(home, ".env")
	if info, err := os.Stat(homeEnv); err == nil && !info.IsDir() {
		return homeEnv, nil
	}
	return "", nil
}

func readEnvFile(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	values := map[string]string{}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		values[strings.ToLower(strings.TrimSpace(key))] = trimEnvValue(value)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return values, nil
}

func applyEnv(cfg *Config, values map[string]string) {
	for key, value := range values {
		switch key {
		case "agent_runtime":
			cfg.AgentRuntime = value
		case "opencode_base_url":
			cfg.OpenCodeBaseURL = value
		case "opencode_provider_id":
			cfg.OpenCodeProviderID = value
		case "opencode_model_id":
			cfg.OpenCodeModelID = value
		case "opencode_enable_event_stream":
			cfg.OpenCodeEnableEventStream = parseBool(value)
		case "opencode_structured_output_mode":
			cfg.OpenCodeStructuredOutputMode = value
		case "opencode_require_prompt_fallback_confirmation":
			cfg.OpenCodeRequirePromptFallbackConfirmation = parseBool(value)
		case "opencode_inject_project_config":
			cfg.OpenCodeInjectProjectConfig = parseBool(value)
		case "opencode_config_path":
			cfg.OpenCodeConfigPath = value
		case "opencode_request_retries":
			cfg.OpenCodeRequestRetries = parseInt(value, cfg.OpenCodeRequestRetries)
		case "external_runtime_timeout_seconds":
			cfg.ExternalRuntimeTimeoutSeconds = parseInt(value, cfg.ExternalRuntimeTimeoutSeconds)
		case "function_concurrency":
			cfg.FunctionConcurrency = parseInt(value, cfg.FunctionConcurrency)
		case "disable_exploit":
			cfg.DisableExploit = parseBool(value)
		case "enable_fallback_audit":
			cfg.EnableFallbackAudit = parseBool(value)
		case "audit_types":
			cfg.AuditTypes = parseList(value)
		case "debug":
			cfg.Debug = parseBool(value)
		case "dry_run":
			cfg.DryRun = parseBool(value)
		case "resume":
			cfg.Resume = parseBool(value)
		case "project_path":
			cfg.ProjectPath = value
		case "scan":
			cfg.Scan = value
		case "entry":
			cfg.Entry = value
		case "attack_surface_skill":
			cfg.AttackSurfaceSkill = value
		case "output_dir":
			cfg.OutputDir = value
		case "target_base_url":
			cfg.TargetBaseURL = value
		}
	}
}

func applyArgs(cfg *Config, args Args) {
	if args.AgentRuntime != "" {
		cfg.AgentRuntime = args.AgentRuntime
	}
	if args.OpenCodeBaseURL != "" {
		cfg.OpenCodeBaseURL = args.OpenCodeBaseURL
	}
	if args.OpenCodeProviderID != "" {
		cfg.OpenCodeProviderID = args.OpenCodeProviderID
	}
	if args.OpenCodeModelID != "" {
		cfg.OpenCodeModelID = args.OpenCodeModelID
	}
	if args.OpenCodeEnableEventStream != nil {
		cfg.OpenCodeEnableEventStream = *args.OpenCodeEnableEventStream
	}
	if args.OpenCodeStructuredOutputMode != "" {
		cfg.OpenCodeStructuredOutputMode = args.OpenCodeStructuredOutputMode
	}
	if args.DisableExploit != nil {
		cfg.DisableExploit = *args.DisableExploit
	}
	if args.EnableFallbackAudit != nil {
		cfg.EnableFallbackAudit = *args.EnableFallbackAudit
	}
	if args.Debug != nil {
		cfg.Debug = *args.Debug
	}
	if args.DryRun != nil {
		cfg.DryRun = *args.DryRun
	}
	if args.Resume != nil {
		cfg.Resume = *args.Resume
	}
	if args.Scan != "" {
		cfg.Scan = args.Scan
	}
	if args.Entry != "" {
		cfg.Entry = args.Entry
	}
	if args.AttackSurfaceSkill != "" {
		cfg.AttackSurfaceSkill = args.AttackSurfaceSkill
	}
	if args.ProjectPath != "" {
		cfg.ProjectPath = args.ProjectPath
	}
	if args.OutputDir != "" {
		cfg.OutputDir = args.OutputDir
	}
	if args.TargetBaseURL != "" {
		cfg.TargetBaseURL = args.TargetBaseURL
	}
	if args.AuditTypes != "" {
		cfg.AuditTypes = parseList(args.AuditTypes)
	}
	if args.FunctionConcurrency > 0 {
		cfg.FunctionConcurrency = args.FunctionConcurrency
	}
}

func parseList(value string) []string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	if strings.HasPrefix(value, "[") {
		var result []string
		if err := json.Unmarshal([]byte(value), &result); err == nil {
			return result
		}
	}
	parts := strings.Split(value, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		item := strings.TrimSpace(part)
		if item != "" {
			result = append(result, item)
		}
	}
	return result
}

func trimEnvValue(value string) string {
	value = stripInlineComment(value)
	value = strings.TrimSpace(value)
	value = strings.TrimSuffix(value, "\r")
	return strings.Trim(value, `"`)
}

func stripInlineComment(value string) string {
	inSingleQuote := false
	inDoubleQuote := false
	escaped := false
	for index, char := range value {
		if escaped {
			escaped = false
			continue
		}
		if char == '\\' {
			escaped = true
			continue
		}
		switch char {
		case '\'':
			if !inDoubleQuote {
				inSingleQuote = !inSingleQuote
			}
		case '"':
			if !inSingleQuote {
				inDoubleQuote = !inDoubleQuote
			}
		case '#':
			if !inSingleQuote && !inDoubleQuote {
				return value[:index]
			}
		}
	}
	return value
}

func parseBool(value string) bool {
	parsed, err := strconv.ParseBool(strings.ToLower(strings.TrimSpace(value)))
	return err == nil && parsed
}

func parseInt(value string, fallback int) int {
	parsed, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil {
		return fallback
	}
	return parsed
}
