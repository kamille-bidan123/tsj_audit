package main

import (
	"flag"
	"fmt"
	"os"

	reportexport "tsj-audit/internal/export"
)

func main() {
	outputDir := flag.String("output-dir", "output", "output directory containing checkpoints")
	inheritSARIF := flag.String("inherit-sarif", "", "old SARIF path whose SARIF Explorer review notes should be inherited")
	flag.Parse()
	if flag.NArg() > 0 {
		*outputDir = flag.Arg(0)
	}
	artifacts, err := reportexport.WriteReportsWithOptions(*outputDir, reportexport.Options{InheritSARIFPath: *inheritSARIF})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(artifacts.JSONPath)
	fmt.Println(artifacts.MarkdownPath)
	fmt.Println(artifacts.HTMLPath)
	fmt.Println(artifacts.SARIFPath)
	fmt.Println(artifacts.IssuesSARIF)
}
