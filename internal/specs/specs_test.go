package specs

import (
	"path/filepath"
	"testing"
)

func TestLoadAuditSpec(t *testing.T) {
	spec, err := LoadFile(filepath.Join("..", "..", "audit_specs", "path_traversal.yaml"))
	if err != nil {
		t.Fatal(err)
	}

	if spec.Name != "path_traversal" {
		t.Fatalf("Name = %q", spec.Name)
	}
	if spec.UserPrompt == "" {
		t.Fatal("expected user prompt")
	}
}

func TestLoadDir(t *testing.T) {
	specs, err := LoadDir(filepath.Join("..", "..", "audit_specs"))
	if err != nil {
		t.Fatal(err)
	}

	if len(specs) < 6 {
		t.Fatalf("expected audit specs, got %d", len(specs))
	}
	if _, ok := specs["command_injection"]; !ok {
		t.Fatalf("missing command_injection in %#v", specs)
	}
	if spec, ok := specs["ioctl_user_buffer_overflow"]; !ok {
		t.Fatalf("missing ioctl_user_buffer_overflow in %#v", specs)
	} else if spec.UserPrompt == "" {
		t.Fatal("ioctl_user_buffer_overflow missing user prompt")
	}
}
