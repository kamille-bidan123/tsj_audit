package status

import (
	"context"
	"net/http"
	"strings"
	"testing"
)

func TestStartStatusService(t *testing.T) {
	service, err := Start("127.0.0.1", 0, New())
	if err != nil {
		if strings.Contains(err.Error(), "operation not permitted") {
			t.Skipf("sandbox does not allow listening sockets: %v", err)
		}
		t.Fatal(err)
	}
	defer service.Stop(context.Background())

	response, err := http.Get(service.URL + "api/status")
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", response.StatusCode)
	}
}
