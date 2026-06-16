package status

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestServerRootServesRuntimeUI(t *testing.T) {
	state := New()

	request := httptest.NewRequest(http.MethodGet, "/", nil)
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d", response.Code)
	}
	body := response.Body.String()
	for _, needle := range []string{"TSJ Audit Runtime", "Runtime Log", "Agent Timer", "OpenCode 权限请求", "Functions", "/api/status", "/api/permission", "/api/select-function", "data-function-key", "hasSelectionInside", "renderedLogLength", "height: 100vh", "overflow: hidden", "follow-float", "scrollLogToBottom"} {
		if !strings.Contains(body, needle) {
			t.Fatalf("page missing %q", needle)
		}
	}
	if strings.Contains(body, "Recent Activity") {
		t.Fatal("page should not show Recent Activity panel")
	}
}

func TestServerSelectFunctionEndpoint(t *testing.T) {
	state := New()
	key := "src/http.c:10:handle"
	state.Log("global")
	state.LogForFunction(key, "function log")

	request := httptest.NewRequest(http.MethodPost, "/api/select-function", bytes.NewBufferString(`{"key":"src/http.c:10:handle"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d", response.Code)
	}
	snapshot := state.Snapshot()
	if snapshot.SelectedFunctionKey != key {
		t.Fatalf("selected = %q", snapshot.SelectedFunctionKey)
	}
	if len(snapshot.Logs) != 1 || snapshot.Logs[0] != "function log" {
		t.Fatalf("logs = %#v", snapshot.Logs)
	}
}

func TestServerStatusEndpoint(t *testing.T) {
	state := New()
	state.SetFunctions([]FunctionStatus{{Name: "handle", File: "src/http.c", Skill: "civetweb_audit", Status: "pending"}})
	state.SetStage("Trace", "handle", "command_injection")

	request := httptest.NewRequest(http.MethodGet, "/api/status", nil)
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	var snapshot Snapshot
	if err := json.NewDecoder(response.Body).Decode(&snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.Stage != "Trace" || snapshot.FunctionName != "handle" {
		t.Fatalf("snapshot = %#v", snapshot)
	}
	if len(snapshot.Functions) != 1 || snapshot.Functions[0].Name != "handle" || snapshot.Functions[0].Status != "running" {
		t.Fatalf("functions = %#v", snapshot.Functions)
	}
}

func TestServerConfirmEndpoint(t *testing.T) {
	state := New()
	state.AskConfirmation("continue?")

	request := httptest.NewRequest(http.MethodPost, "/api/confirm", bytes.NewBufferString(`{"answer":true}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d", response.Code)
	}

	answer, ok := state.ConfirmationAnswer()
	if !ok || !answer {
		t.Fatalf("answer = %v ok = %v", answer, ok)
	}
}

func TestServerPermissionEndpoint(t *testing.T) {
	state := New()
	state.AskPermission(PermissionRequest{ID: "perm-1", SessionID: "session-1", Permission: "edit"})

	request := httptest.NewRequest(http.MethodPost, "/api/permission", bytes.NewBufferString(`{"id":"perm-1","reply":"once"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d", response.Code)
	}
	reply, ok := state.PermissionReply()
	if !ok || reply != "once" {
		t.Fatalf("reply = %q ok = %v", reply, ok)
	}
}

func TestServerPermissionEndpointClearsOnlySelectedRequest(t *testing.T) {
	state := New()
	state.AskPermission(PermissionRequest{ID: "perm-1", SessionID: "session-1", Permission: "read"})
	state.AskPermission(PermissionRequest{ID: "perm-2", SessionID: "session-2", Permission: "bash"})

	request := httptest.NewRequest(http.MethodPost, "/api/permission", bytes.NewBufferString(`{"id":"perm-1","reply":"reject"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	Handler(state).ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d", response.Code)
	}
	snapshot := state.Snapshot()
	if len(snapshot.PermissionRequests) != 1 || snapshot.PermissionRequests[0].ID != "perm-2" {
		t.Fatalf("remaining permissions = %#v", snapshot.PermissionRequests)
	}
}
