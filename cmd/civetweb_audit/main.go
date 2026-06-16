package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"tsj-audit/internal/scanner"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout io.Writer, stderr io.Writer) int {
	if len(args) != 1 {
		fmt.Fprintln(stderr, "usage: civetweb_audit <project_path>")
		return 2
	}
	projectPath, err := filepath.Abs(args[0])
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	entries, ok, err := scanner.RunAttackSurfaceScan("civetweb_audit", projectPath)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	if !ok {
		fmt.Fprintln(stderr, "native scanner unavailable for civetweb_audit")
		return 1
	}
	data, err := json.MarshalIndent(entries, "", "  ")
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	fmt.Fprintln(stdout, string(data))
	return 0
}
