package status

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"
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
	functionLogs          map[string][]string
	selectedFunctionKey   string
	sessionFunctionKeys   map[string]string
	sessionIDsByFunction  map[string][]string
	functionTaskContexts  map[string]taskContext
	confirmationPrompt    string
	confirmationAnswer    bool
	confirmationHasAnswer bool
	permissionRequests    map[string]PermissionRequest
	permissionReplyChs    map[string]chan string
	permissionReply       string
	permissionHasReply    bool
	agentTimer            *agentTimerState
	functionAgentTimers   map[string]*agentTimerState
	functionLogWriter     func(FunctionLogEntry)
}

type taskContext struct {
	stage        string
	functionName string
	auditType    string
}

type FunctionLogEntry struct {
	Time         string `json:"time"`
	EntryKey     string `json:"entry_key"`
	Stage        string `json:"stage,omitempty"`
	FunctionName string `json:"function_name,omitempty"`
	AuditType    string `json:"audit_type,omitempty"`
	SessionID    string `json:"session_id,omitempty"`
	Message      string `json:"message"`
}

type PermissionRequest struct {
	ID         string         `json:"id"`
	SessionID  string         `json:"session_id"`
	Permission string         `json:"permission"`
	Patterns   []string       `json:"patterns,omitempty"`
	Metadata   map[string]any `json:"metadata,omitempty"`
}

type Snapshot struct {
	Stage               string              `json:"stage"`
	FunctionName        string              `json:"function_name"`
	AuditType           string              `json:"audit_type"`
	Runtime             string              `json:"runtime"`
	SessionID           string              `json:"session_id"`
	SelectedFunctionKey string              `json:"selected_function_key,omitempty"`
	Functions           []FunctionStatus    `json:"functions"`
	Logs                []string            `json:"logs"`
	GlobalLogs          []string            `json:"global_logs,omitempty"`
	ConfirmationPrompt  string              `json:"confirmation_prompt,omitempty"`
	PermissionRequest   *PermissionRequest  `json:"permission_request,omitempty"`
	PermissionRequests  []PermissionRequest `json:"permission_requests,omitempty"`
	AgentTimer          *AgentTimerSnapshot `json:"agent_timer,omitempty"`
}

type AgentTimerSnapshot struct {
	Stage                 string `json:"stage"`
	FunctionName          string `json:"function_name"`
	AuditType             string `json:"audit_type"`
	TimeoutMilliseconds   int64  `json:"timeout_milliseconds"`
	ElapsedMilliseconds   int64  `json:"elapsed_milliseconds"`
	RemainingMilliseconds int64  `json:"remaining_milliseconds"`
	Attempt               int    `json:"attempt"`
	MaxAttempts           int    `json:"max_attempts"`
	Paused                bool   `json:"paused"`
	PauseReason           string `json:"pause_reason,omitempty"`
}

type agentTimerState struct {
	stage       string
	function    string
	auditType   string
	timeout     time.Duration
	startedAt   time.Time
	elapsed     time.Duration
	paused      bool
	pauseReason string
	attempt     int
	maxAttempts int
}

type FunctionStatus struct {
	Key        string              `json:"key,omitempty"`
	Name       string              `json:"name"`
	File       string              `json:"file,omitempty"`
	Line       int                 `json:"line,omitempty"`
	Skill      string              `json:"skill,omitempty"`
	Status     string              `json:"status"`
	SessionIDs []string            `json:"session_ids,omitempty"`
	AgentTimer *AgentTimerSnapshot `json:"agent_timer,omitempty"`
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

func (s *Status) SetRuntimeForTask(key, runtime, sessionID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runtime = runtime
	s.sessionID = sessionID
	if key == "" || sessionID == "" {
		return
	}
	if s.sessionFunctionKeys == nil {
		s.sessionFunctionKeys = map[string]string{}
	}
	if s.sessionIDsByFunction == nil {
		s.sessionIDsByFunction = map[string][]string{}
	}
	s.sessionFunctionKeys[sessionID] = key
	if !containsString(s.sessionIDsByFunction[key], sessionID) {
		s.sessionIDsByFunction[key] = append(s.sessionIDsByFunction[key], sessionID)
	}
	s.setFunctionSessionsLocked(key, s.sessionIDsByFunction[key])
}

func (s *Status) FunctionKeyForSession(sessionID string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.sessionFunctionKeys[sessionID]
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

func (s *Status) SetTaskStage(stage, key, functionName, auditType string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stage = stage
	s.functionName = functionName
	s.auditType = auditType
	if key != "" {
		if s.functionTaskContexts == nil {
			s.functionTaskContexts = map[string]taskContext{}
		}
		s.functionTaskContexts[key] = taskContext{
			stage:        stage,
			functionName: functionName,
			auditType:    auditType,
		}
		s.setFunctionStatusByKeyLocked(key, "running")
		return
	}
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

func (s *Status) LogForFunction(key, message string) {
	var writer func(FunctionLogEntry)
	var entry FunctionLogEntry
	s.mu.Lock()
	s.logs = append(s.logs, message)
	if key == "" {
		s.mu.Unlock()
		return
	}
	if s.functionLogs == nil {
		s.functionLogs = map[string][]string{}
	}
	s.functionLogs[key] = append(s.functionLogs[key], message)
	writer = s.functionLogWriter
	task := s.functionTaskContexts[key]
	if task.stage == "" {
		task = taskContext{
			stage:        s.stage,
			functionName: s.functionName,
			auditType:    s.auditType,
		}
	}
	entry = FunctionLogEntry{
		Time:         time.Now().Format(time.RFC3339Nano),
		EntryKey:     key,
		Stage:        task.stage,
		FunctionName: task.functionName,
		AuditType:    task.auditType,
		SessionID:    lastString(s.sessionIDsByFunction[key]),
		Message:      message,
	}
	s.mu.Unlock()
	if writer != nil {
		writer(entry)
	}
}

func (s *Status) SelectFunction(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.selectedFunctionKey = key
}

func (s *Status) SetFunctionLogWriter(writer func(FunctionLogEntry)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.functionLogWriter = writer
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

func (s *Status) SetFunctionStatusByKey(key, status string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.setFunctionStatusByKeyLocked(key, status)
}

func (s *Status) setFunctionStatusByKeyLocked(key, status string) {
	for index := range s.functions {
		if s.functions[index].Key == key {
			s.functions[index].Status = status
			return
		}
	}
	s.functions = append(s.functions, FunctionStatus{Key: key, Name: key, Status: status})
}

func (s *Status) setFunctionSessionsLocked(key string, sessions []string) {
	for index := range s.functions {
		if s.functions[index].Key == key {
			s.functions[index].SessionIDs = append([]string(nil), sessions...)
			return
		}
	}
	s.functions = append(s.functions, FunctionStatus{Key: key, Name: key, Status: "pending", SessionIDs: append([]string(nil), sessions...)})
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
	key := permissionKey(request)
	if s.permissionRequests == nil {
		s.permissionRequests = make(map[string]PermissionRequest)
	}
	if s.permissionReplyChs == nil {
		s.permissionReplyChs = make(map[string]chan string)
	}
	s.permissionRequests[key] = request
	s.permissionReply = "reject"
	s.permissionHasReply = false
	if _, ok := s.permissionReplyChs[key]; !ok {
		s.permissionReplyChs[key] = make(chan string, 1)
	}
	s.pauseAgentTimerLocked(s.sessionFunctionKeys[request.SessionID], "permission")
}

func (s *Status) SetPermissionReply(id, reply string) bool {
	s.mu.Lock()
	key := id
	if key == "" && len(s.permissionRequests) == 1 {
		for existing := range s.permissionRequests {
			key = existing
		}
	}
	replyCh := s.permissionReplyChs[key]
	request, requestExists := s.permissionRequests[key]
	if key == "" || (!requestExists && replyCh == nil) {
		s.mu.Unlock()
		return false
	}
	timerKey := ""
	if requestExists {
		timerKey = s.sessionFunctionKeys[request.SessionID]
	}
	s.permissionReply = reply
	s.permissionHasReply = true
	delete(s.permissionRequests, key)
	delete(s.permissionReplyChs, key)
	if timerKey != "" {
		if !s.hasPendingPermissionForFunctionLocked(timerKey) {
			s.resumeAgentTimerLocked(timerKey)
		}
	} else if len(s.permissionRequests) == 0 {
		s.resumeAgentTimerLocked("")
	}
	s.mu.Unlock()
	if replyCh != nil {
		select {
		case replyCh <- reply:
		default:
		}
	}
	return true
}

func (s *Status) PermissionReply() (string, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.permissionReply, s.permissionHasReply
}

func (s *Status) StartAgentTimer(stage string, timeout time.Duration, attempt, maxAttempts int) {
	s.StartAgentTimerForFunction("", stage, timeout, attempt, maxAttempts)
}

func (s *Status) StartAgentTimerForFunction(key, stage string, timeout time.Duration, attempt, maxAttempts int) {
	if timeout <= 0 {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	if stage == "" {
		stage = s.stage
	}
	task := s.functionTaskContexts[key]
	functionName := s.functionName
	auditType := s.auditType
	if key != "" && task.stage != "" {
		functionName = task.functionName
		auditType = task.auditType
		if stage == "" {
			stage = task.stage
		}
	}
	timer := &agentTimerState{
		stage:       stage,
		function:    functionName,
		auditType:   auditType,
		timeout:     timeout,
		startedAt:   now,
		attempt:     attempt,
		maxAttempts: maxAttempts,
	}
	if key == "" {
		s.agentTimer = timer
	} else {
		if s.functionAgentTimers == nil {
			s.functionAgentTimers = map[string]*agentTimerState{}
		}
		s.functionAgentTimers[key] = timer
	}
	if (key == "" && len(s.permissionRequests) > 0) || (key != "" && s.hasPendingPermissionForFunctionLocked(key)) {
		s.pauseAgentTimerLocked(key, "permission")
	}
}

func (s *Status) StopAgentTimer() {
	s.StopAgentTimerForFunction("")
}

func (s *Status) StopAgentTimerForFunction(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if key != "" {
		delete(s.functionAgentTimers, key)
		return
	}
	s.agentTimer = nil
}

func (s *Status) AgentTimerRemaining() time.Duration {
	return s.AgentTimerRemainingForFunction("")
}

func (s *Status) AgentTimerRemainingForFunction(key string) time.Duration {
	s.mu.Lock()
	defer s.mu.Unlock()
	timer := s.timerLocked(key)
	if timer == nil {
		return 0
	}
	remaining := timer.timeout - agentTimerElapsed(timer, time.Now())
	if remaining < 0 {
		return 0
	}
	return remaining
}

func (s *Status) PauseAgentTimer(reason string) {
	s.PauseAgentTimerForFunction("", reason)
}

func (s *Status) PauseAgentTimerForFunction(key, reason string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.pauseAgentTimerLocked(key, reason)
}

func (s *Status) ResumeAgentTimer() {
	s.ResumeAgentTimerForFunction("")
}

func (s *Status) ResumeAgentTimerForFunction(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.resumeAgentTimerLocked(key)
}

func (s *Status) pauseAgentTimerLocked(key, reason string) {
	timer := s.timerLocked(key)
	if timer == nil || timer.paused {
		return
	}
	now := time.Now()
	timer.elapsed += now.Sub(timer.startedAt)
	timer.paused = true
	timer.pauseReason = reason
}

func (s *Status) resumeAgentTimerLocked(key string) {
	timer := s.timerLocked(key)
	if timer == nil || !timer.paused {
		return
	}
	timer.startedAt = time.Now()
	timer.paused = false
	timer.pauseReason = ""
}

func (s *Status) timerLocked(key string) *agentTimerState {
	if key == "" {
		return s.agentTimer
	}
	return s.functionAgentTimers[key]
}

func (s *Status) hasPendingPermissionForFunctionLocked(key string) bool {
	for _, request := range s.permissionRequests {
		if s.sessionFunctionKeys[request.SessionID] == key {
			return true
		}
	}
	return false
}

func (s *Status) AwaitPermissionReply(ctx context.Context, request PermissionRequest) (string, bool) {
	s.AskPermission(request)
	key := permissionKey(request)
	s.mu.Lock()
	replyCh := s.permissionReplyChs[key]
	s.mu.Unlock()
	select {
	case reply := <-replyCh:
		return reply, true
	case <-ctx.Done():
		s.SetPermissionReply(key, "reject")
		return "reject", false
	}
}

func (s *Status) Snapshot() Snapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	globalLogs := append([]string(nil), s.logs...)
	logs := globalLogs
	if s.selectedFunctionKey != "" {
		logs = append([]string(nil), s.functionLogs[s.selectedFunctionKey]...)
	}
	functions := append([]FunctionStatus(nil), s.functions...)
	for index := range functions {
		if functions[index].Key == "" {
			continue
		}
		functions[index].SessionIDs = append([]string(nil), s.sessionIDsByFunction[functions[index].Key]...)
		functions[index].AgentTimer = agentTimerSnapshot(s.functionAgentTimers[functions[index].Key], now)
	}
	permissions := make([]PermissionRequest, 0, len(s.permissionRequests))
	for _, request := range s.permissionRequests {
		permissions = append(permissions, request)
	}
	sort.Slice(permissions, func(left, right int) bool {
		return permissionKey(permissions[left]) < permissionKey(permissions[right])
	})
	var permission *PermissionRequest
	if len(permissions) > 0 {
		copied := permissions[0]
		permission = &copied
	}
	return Snapshot{
		Stage:               s.stage,
		FunctionName:        s.functionName,
		AuditType:           s.auditType,
		Runtime:             s.runtime,
		SessionID:           s.sessionID,
		SelectedFunctionKey: s.selectedFunctionKey,
		Functions:           functions,
		Logs:                logs,
		GlobalLogs:          globalLogs,
		ConfirmationPrompt:  s.confirmationPrompt,
		PermissionRequest:   permission,
		PermissionRequests:  permissions,
		AgentTimer:          agentTimerSnapshot(s.snapshotAgentTimerLocked(), now),
	}
}

func (s *Status) snapshotAgentTimerLocked() *agentTimerState {
	if s.selectedFunctionKey != "" {
		return s.functionAgentTimers[s.selectedFunctionKey]
	}
	if s.agentTimer != nil {
		return s.agentTimer
	}
	for _, timer := range s.functionAgentTimers {
		return timer
	}
	return nil
}

func (s *Status) agentTimerSnapshotLocked(now time.Time) *AgentTimerSnapshot {
	return agentTimerSnapshot(s.agentTimer, now)
}

func agentTimerSnapshot(timer *agentTimerState, now time.Time) *AgentTimerSnapshot {
	if timer == nil {
		return nil
	}
	elapsed := agentTimerElapsed(timer, now)
	remaining := timer.timeout - elapsed
	if remaining < 0 {
		remaining = 0
	}
	return &AgentTimerSnapshot{
		Stage:                 timer.stage,
		FunctionName:          timer.function,
		AuditType:             timer.auditType,
		TimeoutMilliseconds:   timer.timeout.Milliseconds(),
		ElapsedMilliseconds:   elapsed.Milliseconds(),
		RemainingMilliseconds: remaining.Milliseconds(),
		Attempt:               timer.attempt,
		MaxAttempts:           timer.maxAttempts,
		Paused:                timer.paused,
		PauseReason:           timer.pauseReason,
	}
}

func (s *Status) agentTimerElapsedLocked(now time.Time) time.Duration {
	return agentTimerElapsed(s.agentTimer, now)
}

func agentTimerElapsed(timer *agentTimerState, now time.Time) time.Duration {
	if timer == nil {
		return 0
	}
	elapsed := timer.elapsed
	if !timer.paused {
		elapsed += now.Sub(timer.startedAt)
	}
	if elapsed < 0 {
		return 0
	}
	return elapsed
}

func permissionKey(request PermissionRequest) string {
	if request.ID != "" {
		return request.ID
	}
	return request.SessionID + "|" + request.Permission + "|" + strings.Join(request.Patterns, "\x00")
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func lastString(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return values[len(values)-1]
}
