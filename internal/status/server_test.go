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
	for _, needle := range []string{"TSJ Audit Runtime", "Runtime Log", "OpenCode 权限请求", "Functions", "/api/status", "/api/permission"} {
		if !strings.Contains(body, needle) {
			t.Fatalf("page missing %q", needle)
		}
	}
	if strings.Contains(body, "Recent Activity") {
		t.Fatal("page should not show Recent Activity panel")
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

	request := httptest.NewRequest(http.MethodPost, "/api/permission", bytes.NewBufferString(`{"reply":"once"}`))
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
