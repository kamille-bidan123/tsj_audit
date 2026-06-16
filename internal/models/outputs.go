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
	Confidence     string               `json:"confidence" schema:"minLength=1"`
	Description    string               `json:"description" schema:"minLength=1"`
	Summary        string               `json:"summary"`
	Recommendation *string              `json:"recommendation,omitempty"`
	Findings       []AuditFindingOutput `json:"findings"`
}

type AuditFindingOutput struct {
	FindingID       *string           `json:"finding_id,omitempty"`
	Title           string            `json:"title" schema:"minLength=1"`
	Severity        *string           `json:"severity,omitempty"`
	IsVulnerable    bool              `json:"is_vulnerable"`
	Confidence      string            `json:"confidence" schema:"minLength=1"`
	Description     string            `json:"description" schema:"minLength=1"`
	Recommendation  *string           `json:"recommendation,omitempty"`
	PrimaryLocation FindingLocation   `json:"primary_location"`
	DataFlows       []FindingDataFlow `json:"data_flows"`
}

type ExploitOutput struct {
	Success    bool    `json:"success"`
	PocCommand string  `json:"poc_command"`
	Summary    string  `json:"summary"`
	Error      *string `json:"error,omitempty"`
}
