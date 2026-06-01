package models

type EntrySpec struct {
	FuncName  string  `json:"func_name"`
	FilePath  string  `json:"file_path"`
	Skill     *string `json:"skill,omitempty"`
	StartLine *int    `json:"start_line,omitempty"`
}

type FunctionInfo struct {
	FuncName    string  `json:"func_name"`
	FilePath    string  `json:"file_path"`
	StartLine   int     `json:"start_line"`
	EndLine     int     `json:"end_line"`
	CodeSnippet string  `json:"code_snippet"`
	Skill       *string `json:"skill,omitempty"`
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
	FunctionInfo  FunctionInfo    `json:"function_info"`
	CodeLogic     string          `json:"code_logic"`
	CodeMap       []CodeContext   `json:"code_map"`
	AuditResults  []AuditResult   `json:"audit_results"`
	ExploitResult []ExploitResult `json:"exploit_results"`
}

type AuditResult struct {
	VulnerabilityType string        `json:"vulnerability_type"`
	FindingID         *string       `json:"finding_id,omitempty"`
	Title             *string       `json:"title,omitempty"`
	Severity          *string       `json:"severity,omitempty"`
	IsVulnerable      bool          `json:"is_vulnerable"`
	Confidence        string        `json:"confidence"`
	Description       string        `json:"description"`
	TaintFlow         *string       `json:"taint_flow,omitempty"`
	Recommendation    *string       `json:"recommendation,omitempty"`
	CodeMap           []CodeContext `json:"code_map"`
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
