package models

import (
	"encoding/json"
	"fmt"
)

type EntrySpec struct {
	FuncName  string  `json:"func_name"`
	FilePath  string  `json:"file_path"`
	Skill     *string `json:"skill,omitempty"`
	StartLine *int    `json:"start_line,omitempty"`
}

func (e EntrySpec) Key() string {
	startLine := 0
	if e.StartLine != nil {
		startLine = *e.StartLine
	}
	return fmt.Sprintf("%s:%d:%s", e.FilePath, startLine, e.FuncName)
}

type FunctionInfo struct {
	FuncName    string  `json:"func_name"`
	FilePath    string  `json:"file_path"`
	StartLine   int     `json:"start_line"`
	EndLine     int     `json:"end_line"`
	CodeSnippet string  `json:"code_snippet"`
	Skill       *string `json:"skill,omitempty"`
}

func (f FunctionInfo) Key() string {
	return fmt.Sprintf("%s:%d:%s", f.FilePath, f.StartLine, f.FuncName)
}

type CodeContext struct {
	FunctionName string  `json:"function_name"`
	FilePath     string  `json:"file_path"`
	LineStart    int     `json:"line_start"`
	LineEnd      int     `json:"line_end"`
	CodeSnippet  string  `json:"code_snippet"`
	IsEntryPoint bool    `json:"is_entry_point"`
	TaintSource  *string `json:"taint_source,omitempty"`
	TaintPath    *string `json:"taint_path,omitempty"`
}

type TraceResult struct {
	FunctionInfo       FunctionInfo       `json:"function_info"`
	CodeLogic          string             `json:"code_logic"`
	CodeMap            []CodeContext      `json:"code_map"`
	AuditOutputs       []AuditStageOutput `json:"audit_outputs,omitempty"`
	LegacyAuditResults []AuditResult      `json:"-"`
	ExploitResult      []ExploitResult    `json:"exploit_results"`
}

type AuditStageOutput struct {
	VulnerabilityType string      `json:"vulnerability_type"`
	Output            AuditOutput `json:"output"`
}

func (r *TraceResult) UnmarshalJSON(data []byte) error {
	type traceResultAlias TraceResult
	var decoded struct {
		traceResultAlias
		LegacyAuditResults []AuditResult `json:"audit_results"`
	}
	if err := json.Unmarshal(data, &decoded); err != nil {
		return err
	}
	*r = TraceResult(decoded.traceResultAlias)
	r.LegacyAuditResults = decoded.LegacyAuditResults
	return nil
}

type AuditResult struct {
	VulnerabilityType string            `json:"vulnerability_type"`
	FindingID         *string           `json:"finding_id,omitempty"`
	Title             *string           `json:"title,omitempty"`
	Severity          *string           `json:"severity,omitempty"`
	IsVulnerable      bool              `json:"is_vulnerable"`
	Confidence        string            `json:"confidence"`
	Description       string            `json:"description"`
	Recommendation    *string           `json:"recommendation,omitempty"`
	PrimaryLocation   FindingLocation   `json:"primary_location"`
	DataFlows         []FindingDataFlow `json:"data_flows"`
}

type FindingLocation struct {
	Message      string `json:"message"`
	FunctionName string `json:"function_name"`
	FilePath     string `json:"file_path"`
	LineStart    int    `json:"line_start"`
	LineEnd      int    `json:"line_end"`
}

type FindingDataFlow struct {
	Message string                `json:"message"`
	Steps   []FindingDataFlowStep `json:"steps"`
}

type FindingDataFlowStep struct {
	Role       string `json:"role"`
	Message    string `json:"message"`
	FilePath   string `json:"file_path"`
	LineStart  int    `json:"line_start"`
	LineEnd    int    `json:"line_end"`
	Importance string `json:"importance"`
}

type ExploitResult struct {
	VulnerabilityType string  `json:"vulnerability_type"`
	Success           bool    `json:"success"`
	PocCommand        string  `json:"poc_command"`
	Output            string  `json:"output"`
	Error             *string `json:"error,omitempty"`
}

func StringPtr(value string) *string {
	return &value
}

func IntPtr(value int) *int {
	return &value
}
