package models

type EntryDiscoveryOutput struct {
	Functions []EntrySpec `json:"functions"`
}

type TraceOutput struct {
	FunctionInfo FunctionInfo  `json:"function_info"`
	CodeLogic    string        `json:"code_logic"`
	CodeMap      []CodeContext `json:"code_map"`
}

type AuditOutput struct {
	IsVulnerable   bool                 `json:"is_vulnerable"`
	Confidence     string               `json:"confidence"`
	Description    string               `json:"description"`
	Summary        string               `json:"summary"`
	TaintFlow      *string              `json:"taint_flow,omitempty"`
	Recommendation *string              `json:"recommendation,omitempty"`
	CodeMap        []CodeContext        `json:"code_map"`
	Findings       []AuditFindingOutput `json:"findings"`
}

type AuditFindingOutput struct {
	FindingID      *string       `json:"finding_id,omitempty"`
	Title          string        `json:"title"`
	Severity       *string       `json:"severity,omitempty"`
	IsVulnerable   bool          `json:"is_vulnerable"`
	Confidence     string        `json:"confidence"`
	Description    string        `json:"description"`
	TaintFlow      *string       `json:"taint_flow,omitempty"`
	Recommendation *string       `json:"recommendation,omitempty"`
	CodeMap        []CodeContext `json:"code_map"`
}

type ExploitOutput struct {
	Success    bool    `json:"success"`
	PocCommand string  `json:"poc_command"`
	Summary    string  `json:"summary"`
	Error      *string `json:"error,omitempty"`
}
