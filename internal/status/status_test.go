package status

import "testing"

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

	state.SetPermissionReply("always")
	reply, ok := state.PermissionReply()
	if !ok || reply != "always" {
		t.Fatalf("reply = %q ok = %v", reply, ok)
	}
	if state.Snapshot().PermissionRequest != nil {
		t.Fatal("permission request should be cleared after reply")
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
