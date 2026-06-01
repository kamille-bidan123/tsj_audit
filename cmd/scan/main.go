package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"tsj-audit/internal/scanner"
)

func main() {
	projectPath := flag.String("project-path", ".", "project path")
	skill := flag.String("skill", "civetweb_audit", "attack surface skill")
	flag.Parse()

	entries, ok, err := scanner.RunAttackSurfaceScan(*skill, *projectPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if !ok {
		fmt.Fprintf(os.Stderr, "no native scanner for skill %q\n", *skill)
		os.Exit(2)
	}
	data, err := json.MarshalIndent(entries, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(string(data))
}
