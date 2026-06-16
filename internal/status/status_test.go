package status

import (
	"testing"
	"time"
)

func TestStatusTracksStageAndLogs(t *testing.T) {
	state := New()

	state.SetRuntime("opencode", "session-1")
	state.SetStage("Trace", "handle_request", "path_traversal")
	state.Log("hello")

	snapshot := state.Snapshot()
	if snapshot.Runtime != "opencode" || snapshot.SessionID != "session-1" {
		t.Fatalf("runtime snapshot = %#v", snapshot)
	}
	if snapshot.Stage != "Trace" || snapshot.FunctionName != "handle_request" || snapshot.AuditType != "path_traversal" {
		t.Fatalf("stage snapshot = %#v", snapshot)
	}
	if len(snapshot.Logs) != 1 || snapshot.Logs[0] != "hello" {
		t.Fatalf("logs = %#v", snapshot.Logs)
	}
}

func TestStatusTracksPermissionRequestAndReply(t *testing.T) {
	state := New()
	request := PermissionRequest{
		ID:         "perm-1",
		SessionID:  "session-1",
		Permission: "edit",
		Patterns:   []string{"*.go"},
		Metadata:   map[string]any{"file": "main.go"},
	}

	state.AskPermission(request)
	snapshot := state.Snapshot()
	if snapshot.PermissionRequest == nil || snapshot.PermissionRequest.ID != "perm-1" {
		t.Fatalf("snapshot permission = %#v", snapshot.PermissionRequest)
	}
	if len(snapshot.PermissionRequests) != 1 || snapshot.PermissionRequests[0].ID != "perm-1" {
		t.Fatalf("snapshot permissions = %#v", snapshot.PermissionRequests)
	}

	state.SetPermissionReply("perm-1", "always")
	reply, ok := state.PermissionReply()
	if !ok || reply != "always" {
		t.Fatalf("reply = %q ok = %v", reply, ok)
	}
	if state.Snapshot().PermissionRequest != nil {
		t.Fatal("permission request should be cleared after reply")
	}
}

func TestStatusTracksMultiplePermissionRequests(t *testing.T) {
	state := New()

	state.AskPermission(PermissionRequest{ID: "perm-2", SessionID: "session-2", Permission: "bash"})
	state.AskPermission(PermissionRequest{ID: "perm-1", SessionID: "session-1", Permission: "read"})

	snapshot := state.Snapshot()
	if len(snapshot.PermissionRequests) != 2 {
		t.Fatalf("permissions = %#v", snapshot.PermissionRequests)
	}
	if snapshot.PermissionRequest == nil || snapshot.PermissionRequest.ID != "perm-1" {
		t.Fatalf("compat permission = %#v", snapshot.PermissionRequest)
	}

	state.SetPermissionReply("perm-1", "once")
	snapshot = state.Snapshot()
	if len(snapshot.PermissionRequests) != 1 || snapshot.PermissionRequests[0].ID != "perm-2" {
		t.Fatalf("remaining permissions = %#v", snapshot.PermissionRequests)
	}
}

func TestStatusAgentTimerPausesWhilePermissionIsPending(t *testing.T) {
	state := New()
	state.SetStage("Trace", "handle", "-")
	state.StartAgentTimer("Trace", 120*time.Millisecond, 1, 1)
	time.Sleep(30 * time.Millisecond)

	state.AskPermission(PermissionRequest{ID: "perm-1", SessionID: "session-1", Permission: "bash"})
	paused := state.Snapshot().AgentTimer
	if paused == nil || !paused.Paused {
		t.Fatalf("timer should be paused: %#v", paused)
	}
	remainingWhilePaused := paused.RemainingMilliseconds
	time.Sleep(80 * time.Millisecond)
	stillPaused := state.Snapshot().AgentTimer
	if stillPaused.RemainingMilliseconds < remainingWhilePaused-20 {
		t.Fatalf("remaining time should not drain while paused: before=%d after=%d", remainingWhilePaused, stillPaused.RemainingMilliseconds)
	}

	if !state.SetPermissionReply("perm-1", "once") {
		t.Fatal("permission reply should be accepted")
	}
	resumed := state.Snapshot().AgentTimer
	if resumed == nil || resumed.Paused {
		t.Fatalf("timer should resume after permission reply: %#v", resumed)
	}
}

func TestStatusTracksFunctionAgentTimers(t *testing.T) {
	state := New()
	key := "src/http.c:10:handle"
	state.SetFunctions([]FunctionStatus{{Key: key, Name: "handle", File: "src/http.c", Line: 10, Status: "pending"}})
	state.SetTaskStage("Audit", key, "handle", "password_reset")
	state.StartAgentTimerForFunction(key, "Audit", time.Second, 1, 2)

	snapshot := state.Snapshot()
	if snapshot.AgentTimer == nil || snapshot.AgentTimer.FunctionName != "handle" {
		t.Fatalf("fallback function timer = %#v", snapshot.AgentTimer)
	}
	if len(snapshot.Functions) != 1 || snapshot.Functions[0].AgentTimer == nil {
		t.Fatalf("function timer missing = %#v", snapshot.Functions)
	}
	if snapshot.Functions[0].AgentTimer.MaxAttempts != 2 {
		t.Fatalf("function timer attempts = %#v", snapshot.Functions[0].AgentTimer)
	}

	state.SelectFunction(key)
	snapshot = state.Snapshot()
	if snapshot.AgentTimer == nil || snapshot.AgentTimer.Stage != "Audit" {
		t.Fatalf("selected function timer = %#v", snapshot.AgentTimer)
	}

	state.StopAgentTimerForFunction(key)
	if state.Snapshot().AgentTimer != nil {
		t.Fatal("selected function timer should clear after stop")
	}
}

func TestStatusPausesOnlyMatchingFunctionTimerForPermission(t *testing.T) {
	state := New()
	firstKey := "src/one.c:10:first"
	secondKey := "src/two.c:20:second"
	state.SetFunctions([]FunctionStatus{
		{Key: firstKey, Name: "first", Status: "pending"},
		{Key: secondKey, Name: "second", Status: "pending"},
	})
	state.SetRuntimeForTask(firstKey, "opencode", "session-1")
	state.SetRuntimeForTask(secondKey, "opencode", "session-2")
	state.SetTaskStage("Audit", firstKey, "first", "-")
	state.StartAgentTimerForFunction(firstKey, "Audit", time.Second, 1, 1)
	state.SetTaskStage("Audit", secondKey, "second", "-")
	state.StartAgentTimerForFunction(secondKey, "Audit", time.Second, 1, 1)

	state.AskPermission(PermissionRequest{ID: "perm-1", SessionID: "session-1", Permission: "read"})
	snapshot := state.Snapshot()
	if !snapshot.Functions[0].AgentTimer.Paused {
		t.Fatalf("first function timer should pause = %#v", snapshot.Functions[0].AgentTimer)
	}
	if snapshot.Functions[1].AgentTimer.Paused {
		t.Fatalf("second function timer should keep running = %#v", snapshot.Functions[1].AgentTimer)
	}

	state.SetPermissionReply("perm-1", "once")
	snapshot = state.Snapshot()
	if snapshot.Functions[0].AgentTimer.Paused {
		t.Fatalf("first function timer should resume = %#v", snapshot.Functions[0].AgentTimer)
	}
}

func TestStatusTracksFunctions(t *testing.T) {
	state := New()
	state.SetFunctions([]FunctionStatus{
		{Name: "handle_one", File: "src/one.c", Skill: "civetweb_audit", Status: "pending"},
		{Name: "handle_two", File: "src/two.c", Skill: "civetweb_audit", Status: "pending"},
	})

	state.SetStage("Trace", "handle_one", "-")
	state.SetFunctionStatus("handle_two", "done")

	snapshot := state.Snapshot()
	if len(snapshot.Functions) != 2 {
		t.Fatalf("functions = %#v", snapshot.Functions)
	}
	if snapshot.Functions[0].Status != "running" {
		t.Fatalf("first function = %#v", snapshot.Functions[0])
	}
	if snapshot.Functions[1].Status != "done" {
		t.Fatalf("second function = %#v", snapshot.Functions[1])
	}
}

func TestStatusSelectsFunctionLogsAndTracksSession(t *testing.T) {
	state := New()
	key := "src/http.c:10:handle"
	state.SetFunctions([]FunctionStatus{{Key: key, Name: "handle", File: "src/http.c", Line: 10, Status: "pending"}})
	state.SetRuntimeForTask(key, "opencode", "session-1")
	state.Log("global")
	state.LogForFunction(key, "function log")

	snapshot := state.Snapshot()
	if len(snapshot.Logs) != 2 || len(snapshot.GlobalLogs) != 2 {
		t.Fatalf("global logs = %#v", snapshot)
	}
	if got := state.FunctionKeyForSession("session-1"); got != key {
		t.Fatalf("session key = %q", got)
	}
	if len(snapshot.Functions) != 1 || len(snapshot.Functions[0].SessionIDs) != 1 || snapshot.Functions[0].SessionIDs[0] != "session-1" {
		t.Fatalf("function sessions = %#v", snapshot.Functions)
	}

	state.SelectFunction(key)
	snapshot = state.Snapshot()
	if snapshot.SelectedFunctionKey != key {
		t.Fatalf("selected key = %q", snapshot.SelectedFunctionKey)
	}
	if len(snapshot.Logs) != 1 || snapshot.Logs[0] != "function log" {
		t.Fatalf("selected logs = %#v", snapshot.Logs)
	}
}

func TestStatusFunctionLogWriterUsesPerFunctionTaskContext(t *testing.T) {
	state := New()
	firstKey := "src/one.c:10:first"
	secondKey := "src/two.c:20:second"
	var entries []FunctionLogEntry
	state.SetFunctionLogWriter(func(entry FunctionLogEntry) {
		entries = append(entries, entry)
	})

	state.SetTaskStage("Audit", firstKey, "first", "command_injection")
	state.SetTaskStage("Trace", secondKey, "second", "-")
	state.LogForFunction(firstKey, "first audit log")

	if len(entries) != 1 {
		t.Fatalf("entries = %#v", entries)
	}
	if entries[0].Stage != "Audit" || entries[0].FunctionName != "first" || entries[0].AuditType != "command_injection" {
		t.Fatalf("entry used global task context = %#v", entries[0])
	}
}
