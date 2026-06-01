package extensions

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestServerStateListsAuditSpecsAndSkills(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "web/extensions_manager.html", "<html></html>")
	writeFile(t, root, "audit_specs/path_traversal.yaml", "name: path_traversal\nuser_prompt: |\n  check paths\n")
	writeFile(t, root, "skills/attack_surface/civetweb_audit/SKILL.md", "---\nname: civetweb_audit\nrequired_audit_types:\n  - path_traversal\n---\n\n# Civet\n\n## 攻击面发现知识\n\nroutes\n\n## 外部输入知识\n\nrequests\n\n## PoC 生成知识\n\ncurl\n")
	writeFile(t, root, "skills/rpc/SKILL.md", "---\nname: rpc\n---\n\nbody\n")

	request := httptest.NewRequest(http.MethodGet, "/api/state", nil)
	response := httptest.NewRecorder()
	NewServer(root).Handler().ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", response.Code, response.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if len(body["audit_specs"].([]any)) != 1 {
		t.Fatalf("body = %#v", body)
	}
	if len(body["attack_surface_skills"].([]any)) != 1 {
		t.Fatalf("body = %#v", body)
	}
	if len(body["skills"].([]any)) != 1 {
		t.Fatalf("body = %#v", body)
	}
}

func TestServerCreatesAuditSpec(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "web/extensions_manager.html", "<html></html>")
	payload := []byte(`{"id":"xss","name":"xss","user_prompt":"check xss"}`)
	request := httptest.NewRequest(http.MethodPost, "/api/audit-specs", bytes.NewReader(payload))
	response := httptest.NewRecorder()

	NewServer(root).Handler().ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d body=%s", response.Code, response.Body.String())
	}
	data, err := os.ReadFile(filepath.Join(root, "audit_specs", "xss.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(data, []byte("user_prompt: |")) {
		t.Fatalf("spec = %s", data)
	}
}

func writeFile(t *testing.T, root string, rel string, content string) {
	t.Helper()
	path := filepath.Join(root, rel)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}
