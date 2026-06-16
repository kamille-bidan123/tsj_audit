package status

import (
	"context"
	"net"
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

func TestListenAvailableReturnsActualPortForDynamicPort(t *testing.T) {
	listener, port, err := listenAvailable("127.0.0.1", 0, 1)
	if err != nil {
		if strings.Contains(err.Error(), "operation not permitted") {
			t.Skipf("sandbox does not allow listening sockets: %v", err)
		}
		t.Fatal(err)
	}
	defer listener.Close()

	if port == 0 {
		t.Fatalf("port = 0, want actual listener port from %s", listener.Addr())
	}
	if tcpAddr, ok := listener.Addr().(*net.TCPAddr); !ok || tcpAddr.Port != port {
		t.Fatalf("listener addr = %v, returned port = %d", listener.Addr(), port)
	}
}

type testListener struct {
	net.Listener
	addr net.Addr
}

func (l testListener) Addr() net.Addr {
	return l.addr
}

func TestListenerPortUsesTCPAddrPort(t *testing.T) {
	got := listenerPort(testListener{addr: &net.TCPAddr{IP: net.ParseIP("127.0.0.1"), Port: 43210}}, 0)
	if got != 43210 {
		t.Fatalf("port = %d, want 43210", got)
	}
}
