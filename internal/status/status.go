package status

import (
	"context"
	"sync"
)

type Status struct {
	mu                    sync.Mutex
	stage                 string
	functionName          string
	auditType             string
	runtime               string
	sessionID             string
	functions             []FunctionStatus
	logs                  []string
	confirmationPrompt    string
	confirmationAnswer    bool
	confirmationHasAnswer bool
	permissionRequest     *PermissionRequest
	permissionReply       string
	permissionHasReply    bool
	permissionReplyCh     chan string
}

type PermissionRequest struct {
	ID         string         `json:"id"`
	SessionID  string         `json:"session_id"`
	Permission string         `json:"permission"`
	Patterns   []string       `json:"patterns,omitempty"`
	Metadata   map[string]any `json:"metadata,omitempty"`
}

type Snapshot struct {
	Stage              string             `json:"stage"`
	FunctionName       string             `json:"function_name"`
	AuditType          string             `json:"audit_type"`
	Runtime            string             `json:"runtime"`
	SessionID          string             `json:"session_id"`
	Functions          []FunctionStatus   `json:"functions"`
	Logs               []string           `json:"logs"`
	ConfirmationPrompt string             `json:"confirmation_prompt,omitempty"`
	PermissionRequest  *PermissionRequest `json:"permission_request,omitempty"`
}

type FunctionStatus struct {
	Name   string `json:"name"`
	File   string `json:"file,omitempty"`
	Line   int    `json:"line,omitempty"`
	Skill  string `json:"skill,omitempty"`
	Status string `json:"status"`
}

func New() *Status {
	return &Status{}
}

func (s *Status) SetRuntime(runtime, sessionID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runtime = runtime
	s.sessionID = sessionID
}

func (s *Status) SetStage(stage, functionName, auditType string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stage = stage
	s.functionName = functionName
	s.auditType = auditType
	if functionName != "" && functionName != "-" {
		s.setFunctionStatusLocked(functionName, "running")
	}
}

func (s *Status) Heartbeat(message string) {
	s.Log(message)
}

func (s *Status) Log(message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.logs = append(s.logs, message)
}

func (s *Status) SetFunctions(functions []FunctionStatus) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.functions = append([]FunctionStatus(nil), functions...)
}

func (s *Status) SetFunctionStatus(name, status string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.setFunctionStatusLocked(name, status)
}

func (s *Status) setFunctionStatusLocked(name, status string) {
	for index := range s.functions {
		if s.functions[index].Name == name {
			s.functions[index].Status = status
			return
		}
	}
	s.functions = append(s.functions, FunctionStatus{Name: name, Status: status})
}

func (s *Status) AskConfirmation(prompt string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.confirmationPrompt = prompt
	s.confirmationHasAnswer = false
}

func (s *Status) SetConfirmationAnswer(answer bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.confirmationAnswer = answer
	s.confirmationHasAnswer = true
	s.confirmationPrompt = ""
}

func (s *Status) ConfirmationAnswer() (bool, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.confirmationAnswer, s.confirmationHasAnswer
}

func (s *Status) AskPermission(request PermissionRequest) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.permissionRequest = &request
	s.permissionReply = "reject"
	s.permissionHasReply = false
	s.permissionReplyCh = make(chan string, 1)
}

func (s *Status) SetPermissionReply(reply string) {
	s.mu.Lock()
	replyCh := s.permissionReplyCh
	s.permissionReply = reply
	s.permissionHasReply = true
	s.permissionRequest = nil
	s.permissionReplyCh = nil
	s.mu.Unlock()
	if replyCh != nil {
		select {
		case replyCh <- reply:
		default:
		}
	}
}

func (s *Status) PermissionReply() (string, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.permissionReply, s.permissionHasReply
}

func (s *Status) AwaitPermissionReply(ctx context.Context, request PermissionRequest) (string, bool) {
	s.AskPermission(request)
	s.mu.Lock()
	replyCh := s.permissionReplyCh
	s.mu.Unlock()
	select {
	case reply := <-replyCh:
		return reply, true
	case <-ctx.Done():
		s.SetPermissionReply("reject")
		return "reject", false
	}
}

func (s *Status) Snapshot() Snapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	logs := append([]string(nil), s.logs...)
	functions := append([]FunctionStatus(nil), s.functions...)
	var permission *PermissionRequest
	if s.permissionRequest != nil {
		copied := *s.permissionRequest
		permission = &copied
	}
	return Snapshot{
		Stage:              s.stage,
		FunctionName:       s.functionName,
		AuditType:          s.auditType,
		Runtime:            s.runtime,
		SessionID:          s.sessionID,
		Functions:          functions,
		Logs:               logs,
		ConfirmationPrompt: s.confirmationPrompt,
		PermissionRequest:  permission,
	}
}
