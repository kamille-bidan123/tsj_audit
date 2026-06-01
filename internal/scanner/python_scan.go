package scanner

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"tsj-audit/internal/models"
)

const pythonScanWrapper = `
import importlib.util
import json
import sys
import traceback
import contextlib

scan_path = sys.argv[1]
project_path = sys.argv[2]

try:
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location("scan_module", scan_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        results = module.scan_directory(project_path)
    print(json.dumps(results, ensure_ascii=False))
except Exception:
    traceback.print_exc()
    sys.exit(1)
`

func RunPythonScan(ctx context.Context, scanPath, projectPath string) ([]models.EntrySpec, error) {
	root := findPythonScanRoot(scanPath)
	interpreter := "python3"
	if root != "" {
		venvPython := filepath.Join(root, ".venv", "bin", "python")
		if _, err := os.Stat(venvPython); err == nil {
			interpreter = venvPython
		}
	}
	command := exec.CommandContext(ctx, interpreter, "-c", pythonScanWrapper, scanPath, projectPath)
	if root != "" {
		command.Dir = root
	}
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr

	if err := command.Run(); err != nil {
		return nil, fmt.Errorf("python scan failed: %w: %s", err, stderr.String())
	}

	var entries []models.EntrySpec
	if err := json.Unmarshal(stdout.Bytes(), &entries); err != nil {
		return nil, fmt.Errorf("decode python scan output: %w", err)
	}
	return entries, nil
}

func findPythonScanRoot(scanPath string) string {
	dir := filepath.Dir(scanPath)
	if !filepath.IsAbs(dir) {
		abs, err := filepath.Abs(dir)
		if err == nil {
			dir = abs
		}
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "models.py")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return ""
		}
		dir = parent
	}
}
