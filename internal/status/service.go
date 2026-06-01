package status

import (
	"context"
	"fmt"
	"net"
	"net/http"
)

type Service struct {
	State  *Status
	Server *http.Server
	URL    string
}

func Start(host string, startPort int, state *Status) (*Service, error) {
	if state == nil {
		state = New()
	}
	listener, port, err := listenAvailable(host, startPort, 20)
	if err != nil {
		return nil, err
	}
	server := &http.Server{Handler: Handler(state)}
	service := &Service{
		State:  state,
		Server: server,
		URL:    fmt.Sprintf("http://%s:%d/", host, port),
	}
	go func() {
		_ = server.Serve(listener)
	}()
	return service, nil
}

func (s *Service) Stop(ctx context.Context) error {
	if s == nil || s.Server == nil {
		return nil
	}
	return s.Server.Shutdown(ctx)
}

func listenAvailable(host string, startPort int, attempts int) (net.Listener, int, error) {
	var lastErr error
	for port := startPort; port < startPort+attempts; port++ {
		listener, err := net.Listen("tcp", fmt.Sprintf("%s:%d", host, port))
		if err == nil {
			return listener, port, nil
		}
		lastErr = err
	}
	return nil, 0, fmt.Errorf("no available status port starting at %d: %w", startPort, lastErr)
}
