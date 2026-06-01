package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"tsj-audit/internal/checkpoint"
	"tsj-audit/internal/config"
	reportexport "tsj-audit/internal/export"
	"tsj-audit/internal/opencodeconfig"
	"tsj-audit/internal/pipeline"
	"tsj-audit/internal/runtime"
	"tsj-audit/internal/status"
)

func main() {
	if err := run(os.Stderr, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(stderr io.Writer, args []string) error {
	if isHelpRequest(args) {
		_, err := loadConfigWithOutput(args, stderr)
		return err
	}
	cfg, err := loadConfig(args)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintln(stderr, "tsj-audit Go refactor"); err != nil {
		return err
	}
	if _, err := fmt.Fprintf(stderr, "runtime=%s output=%s\n", cfg.AgentRuntime, cfg.OutputDir); err != nil {
		return err
	}
	if cfg.Scan == "" && cfg.Entry == "" && cfg.AttackSurfaceSkill == "" {
		return nil
	}
	runCtx := context.Background()
	if cfg.ExternalRuntimeTimeoutSeconds > 0 {
		var cancel context.CancelFunc
		runCtx, cancel = context.WithTimeout(runCtx, time.Duration(cfg.ExternalRuntimeTimeoutSeconds)*time.Second)
		defer cancel()
	}
	state := status.New()
	service := startStatusService(stderr, state)
	if service != nil {
		defer service.Stop(context.Background())
	}
	client, err := createRuntime(cfg)
	if err != nil {
		return err
	}
	if cfg.DryRun {
		_, _ = fmt.Fprintln(stderr, "[dry-run] runtime constructed and configuration loaded")
		return nil
	}
	if cfg.AgentRuntime == "opencode" && cfg.OpenCodeInjectProjectConfig {
		path, err := opencodeconfig.Ensure(cfg.OpenCodeConfigPath, cfg.ProjectPath)
		if err != nil {
			return err
		}
		_, _ = fmt.Fprintf(stderr, "[opencode] configured official permissions in %s for project %s\n", path, cfg.ProjectPath)
	}
	if checker, ok := client.(runtime.HealthChecker); ok {
		if err := checker.HealthCheck(runCtx); err != nil {
			return err
		}
	}
	if opencode, ok := client.(*runtime.OpenCode); ok && cfg.OpenCodeStructuredOutputMode == "auto" {
		mode, err := opencode.ProbeStructuredOutput(runCtx)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "[opencode] structured output probe failed; using prompt mode: %v\n", err)
			if cfg.OpenCodeRequirePromptFallbackConfirmation {
				if service == nil {
					return fmt.Errorf("opencode prompt JSON fallback requires confirmation, but the status page is unavailable; set opencode_require_prompt_fallback_confirmation=false to continue without the Web confirmation step")
				}
				_, _ = fmt.Fprintln(stderr, "[opencode] waiting for confirmation on the status page before continuing with prompt JSON fallback")
				state.AskConfirmation("OpenCode structured output probe failed; continue with prompt JSON fallback?")
				confirmed, waitErr := waitForStatusConfirmation(runCtx, state)
				if waitErr != nil {
					return waitErr
				}
				if !confirmed {
					return fmt.Errorf("opencode prompt JSON fallback was rejected")
				}
				_, _ = fmt.Fprintln(stderr, "[opencode] prompt JSON fallback confirmed; continuing")
			}
		} else {
			_, _ = fmt.Fprintf(stderr, "[opencode] structured output mode: %s\n", mode)
		}
	}
	if err := rejectExistingCheckpoints(cfg); err != nil {
		return err
	}
	if err := saveConfig(cfg); err != nil {
		return err
	}
	if err := pipeline.Run(runCtx, pipeline.Options{
		Config:      cfg,
		Runtime:     client,
		Status:      state,
		Checkpoints: checkpoint.Store{OutputDir: cfg.OutputDir},
	}); err != nil {
		return err
	}
	_, err = reportexport.WriteReports(cfg.OutputDir)
	return err
}

func isHelpRequest(args []string) bool {
	for _, arg := range args {
		if arg == "--help" || arg == "-h" {
			return true
		}
	}
	return false
}

func startStatusService(stderr io.Writer, state *status.Status) *status.Service {
	service, err := status.Start("127.0.0.1", 8765, state)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "[Web UI] status server unavailable: %v\n", err)
		return nil
	}
	_, _ = fmt.Fprintf(stderr, "[Web UI] status page: %s\n", service.URL)
	return service
}

func rejectExistingCheckpoints(cfg config.Config) error {
	if cfg.Resume || cfg.OutputDir == "" {
		return nil
	}
	entries, err := os.ReadDir(filepath.Join(cfg.OutputDir, "checkpoints"))
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".json" {
			return fmt.Errorf("existing checkpoints found in %s; use --resume or choose a new --output-dir", cfg.OutputDir)
		}
	}
	return nil
}

func saveConfig(cfg config.Config) error {
	if cfg.OutputDir == "" {
		return nil
	}
	if err := os.MkdirAll(cfg.OutputDir, 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(cfg.OutputDir, "audit_config.json"), data, 0644)
}

func createRuntime(cfg config.Config) (runtime.Client, error) {
	switch cfg.AgentRuntime {
	case "mock":
		return runtime.NewEchoTraceMock(), nil
	case "opencode":
		return runtime.NewOpenCodeWithOptions(runtime.OpenCodeOptions{
			BaseURL:              cfg.OpenCodeBaseURL,
			ProviderID:           cfg.OpenCodeProviderID,
			ModelID:              cfg.OpenCodeModelID,
			ProjectDir:           cfg.ProjectPath,
			EnableEventStream:    cfg.OpenCodeEnableEventStream,
			StructuredOutputMode: cfg.OpenCodeStructuredOutputMode,
			HTTPClient:           &http.Client{Timeout: time.Duration(cfg.ExternalRuntimeTimeoutSeconds) * time.Second},
		}), nil
	case "codex", "claudecode":
		return runtime.Command{
			Name:       cfg.AgentRuntime,
			ProjectDir: cfg.ProjectPath,
			Timeout:    time.Duration(cfg.ExternalRuntimeTimeoutSeconds) * time.Second,
		}, nil
	default:
		return nil, fmt.Errorf("unsupported runtime %q", cfg.AgentRuntime)
	}
}

func waitForStatusConfirmation(ctx context.Context, state *status.Status) (bool, error) {
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	for {
		answer, ok := state.ConfirmationAnswer()
		if ok {
			return answer, nil
		}
		select {
		case <-ctx.Done():
			return false, fmt.Errorf("waiting for status-page confirmation: %w", ctx.Err())
		case <-ticker.C:
		}
	}
}

func loadConfig(args []string) (config.Config, error) {
	return loadConfigWithOutput(args, io.Discard)
}

func loadConfigWithOutput(args []string, output io.Writer) (config.Config, error) {
	flags := flag.NewFlagSet("tsj-audit", flag.ContinueOnError)
	flags.SetOutput(output)

	var cli config.Args
	flags.StringVar(&cli.ConfigFile, "config", "", "config file")
	flags.StringVar(&cli.AgentRuntime, "agent-runtime", "", "agent runtime")
	flags.StringVar(&cli.OpenCodeBaseURL, "opencode-base-url", "", "opencode base URL")
	flags.StringVar(&cli.OpenCodeProviderID, "opencode-provider-id", "", "opencode provider ID")
	flags.StringVar(&cli.OpenCodeModelID, "opencode-model-id", "", "opencode model ID")
	flags.StringVar(&cli.OpenCodeStructuredOutputMode, "opencode-structured-output-mode", "", "opencode structured output mode")
	flags.StringVar(&cli.Scan, "scan", "", "scan script")
	flags.StringVar(&cli.Entry, "entry", "", "entry JSON")
	flags.StringVar(&cli.AttackSurfaceSkill, "attack-surface-skill", "", "attack surface skill")
	flags.StringVar(&cli.ProjectPath, "project-path", "", "project path")
	flags.StringVar(&cli.OutputDir, "output-dir", "", "output directory")
	flags.StringVar(&cli.TargetBaseURL, "target-base-url", "", "target base URL")
	flags.StringVar(&cli.AuditTypes, "audit-types", "", "audit types")

	disableExploit := flags.Bool("disable-exploit", false, "disable exploit stage")
	enableFallbackAudit := flags.Bool("enable-fallback-audit", false, "enable fallback audit")
	opencodeEnableEventStream := flags.Bool("opencode-enable-event-stream", false, "enable opencode /event SSE listener")
	debug := flags.Bool("debug", false, "enable debug mode")
	dryRun := flags.Bool("dry-run", false, "validate config and runtime setup without running audit stages")
	resume := flags.Bool("resume", false, "resume from checkpoints")

	if err := flags.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return config.Config{}, nil
		}
		return config.Config{}, err
	}
	if flagWasProvided(flags, "disable-exploit") {
		cli.DisableExploit = disableExploit
	}
	if flagWasProvided(flags, "enable-fallback-audit") {
		cli.EnableFallbackAudit = enableFallbackAudit
	}
	if flagWasProvided(flags, "opencode-enable-event-stream") {
		cli.OpenCodeEnableEventStream = opencodeEnableEventStream
	}
	if flagWasProvided(flags, "debug") {
		cli.Debug = debug
	}
	if flagWasProvided(flags, "dry-run") {
		cli.DryRun = dryRun
	}
	if flagWasProvided(flags, "resume") {
		cli.Resume = resume
	}
	return config.Load(cli)
}

func flagWasProvided(flags *flag.FlagSet, name string) bool {
	found := false
	flags.Visit(func(flag *flag.Flag) {
		if flag.Name == name {
			found = true
		}
	})
	return found
}
