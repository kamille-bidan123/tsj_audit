package runtime

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"tsj-audit/internal/status"
)

func TestOpenCodeRunJSONCreatesMessagesAndDeletesSession(t *testing.T) {
	var calls []string
	client := NewOpenCode("http://opencode.local", &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			calls = append(calls, req.Method+" "+req.URL.Path)
			switch req.Method + " " + req.URL.Path {
			case "POST /session":
				return jsonResponse(200, `{"id":"session-1"}`), nil
			case "POST /session/session-1/message":
				var body map[string]any
				if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
					t.Fatal(err)
				}
				if _, ok := body["parts"]; !ok {
					t.Fatalf("missing parts in %#v", body)
				}
				return jsonResponse(200, `{"assistant":"ok"}`), nil
			case "DELETE /session/session-1":
				return jsonResponse(200, `{}`), nil
			default:
				t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				return nil, nil
			}
		}),
	})

	raw, messages, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"assistant":"ok"}` {
		t.Fatalf("raw = %s", raw)
	}
	if len(messages) != 1 || messages[0].Content != `{"assistant":"ok"}` {
		t.Fatalf("messages = %#v", messages)
	}
	want := []string{
		"POST /session",
		"POST /session/session-1/message",
		"DELETE /session/session-1",
	}
	if !equalStrings(calls, want) {
		t.Fatalf("calls = %#v, want %#v", calls, want)
	}
}

func TestOpenCodeRunJSONExtractsStructuredPayloadFromEnvelope(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:              "http://opencode.local",
		StructuredOutputMode: "json_schema",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "POST /session/session-1/message":
					return jsonResponse(200, `{"info":{"structured":{"ok":true}},"parts":[{"type":"tool","tool":"StructuredOutput","state":{"input":{"ok":true}}}]}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	raw, messages, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Schema:     json.RawMessage(`{"type":"object"}`),
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"ok":true}` {
		t.Fatalf("raw = %s", raw)
	}
	if len(messages) != 1 || !bytes.Contains([]byte(messages[0].Content), []byte(`"structured":{"ok":true}`)) {
		t.Fatalf("messages = %#v", messages)
	}
}

func TestOpenCodeCreatesSessionWithProjectDirectory(t *testing.T) {
	projectDir := t.TempDir()
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:    "http://opencode.local",
		ProjectDir: projectDir,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					if req.Body != nil {
						data, err := io.ReadAll(req.Body)
						if err != nil {
							t.Fatal(err)
						}
						if strings.TrimSpace(string(data)) != "" {
							t.Fatalf("session body = %s", data)
						}
					}
					if req.Header.Get("x-opencode-directory") != url.PathEscape(projectDir) {
						t.Fatalf("directory header = %q", req.Header.Get("x-opencode-directory"))
					}
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "POST /session/session-1/message":
					if req.Header.Get("x-opencode-directory") != url.PathEscape(projectDir) {
						t.Fatalf("directory header = %q", req.Header.Get("x-opencode-directory"))
					}
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	if _, _, err := client.RunJSON(context.Background(), RunJSONRequest{StageName: "Trace", UserPrompt: "hello"}); err != nil {
		t.Fatal(err)
	}
}

func TestOpenCodeRunJSONUpdatesRuntimeStatus(t *testing.T) {
	state := status.New()
	client := NewOpenCode("http://opencode.local", &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			switch req.Method + " " + req.URL.Path {
			case "POST /session":
				return jsonResponse(200, `{"id":"session-1"}`), nil
			case "POST /session/session-1/message":
				return jsonResponse(200, `{"assistant":"ok"}`), nil
			case "GET /permission":
				return jsonResponse(200, `[]`), nil
			case "DELETE /session/session-1":
				return jsonResponse(200, `{}`), nil
			default:
				t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				return nil, nil
			}
		}),
	})

	_, _, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
	snapshot := state.Snapshot()
	if snapshot.Runtime != "opencode" || snapshot.SessionID != "session-1" {
		t.Fatalf("snapshot runtime/session = %q/%q", snapshot.Runtime, snapshot.SessionID)
	}
}

func TestOpenCodeRunJSONPollsPermissionsDuringSession(t *testing.T) {
	state := status.New()
	replied := make(chan struct{})
	replyWhenAsked(t, state, "reject")
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /permission":
					return jsonResponse(200, `[{"id":"perm-1","sessionID":"session-1","permission":"edit"}]`), nil
				case "POST /permission/perm-1/reply":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					if body["response"] != "reject" {
						t.Fatalf("body = %#v", body)
					}
					close(replied)
					return jsonResponse(200, `{"ok":true}`), nil
				case "POST /session/session-1/message":
					select {
					case <-replied:
					case <-time.After(time.Second):
						t.Fatal("permission poll did not reply before message")
					}
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	_, _, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
	if state.Snapshot().PermissionRequest != nil {
		t.Fatal("permission should be cleared after reply")
	}
}

func TestOpenCodeRunJSONHandlesPermissionEventStream(t *testing.T) {
	state := status.New()
	replyWhenAsked(t, state, "once")
	replied := make(chan struct{})
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:           "http://opencode.local",
		EnableEventStream: true,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /event":
					return jsonResponse(200, "data: {\"type\":\"permission.asked\",\"properties\":{\"id\":\"perm-1\",\"sessionID\":\"session-1\",\"permission\":\"edit\"}}\n\n"), nil
				case "GET /permission":
					return jsonResponse(200, `[]`), nil
				case "POST /permission/perm-1/reply":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					if body["response"] != "once" {
						t.Fatalf("body = %#v", body)
					}
					close(replied)
					return jsonResponse(200, `{"ok":true}`), nil
				case "POST /session/session-1/message":
					select {
					case <-replied:
					case <-time.After(time.Second):
						t.Fatal("event stream did not reply before message")
					}
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	_, _, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestOpenCodeRunJSONIncludesModelAndJSONSchemaFormat(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:              "http://opencode.local",
		ProviderID:           "openai",
		ModelID:              "gpt-test",
		StructuredOutputMode: "json_schema",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "POST /session/session-1/message":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					model, ok := body["model"].(map[string]any)
					if !ok || model["providerID"] != "openai" || model["modelID"] != "gpt-test" {
						t.Fatalf("model = %#v", body["model"])
					}
					format, ok := body["format"].(map[string]any)
					if !ok || format["type"] != "json_schema" {
						t.Fatalf("format = %#v", body["format"])
					}
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	_, _, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Schema:     json.RawMessage(`{"type":"object","properties":{"ok":{"type":"boolean"}}}`),
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestOpenCodeHealthCheckRequiresSessionID(t *testing.T) {
	client := NewOpenCode("http://opencode.local", &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return jsonResponse(200, `{"data":{}}`), nil
		}),
	})

	if err := client.HealthCheck(context.Background()); err == nil {
		t.Fatal("expected missing session id error")
	}
}

func TestOpenCodeProbeStructuredOutputSetsJSONSchemaMode(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:              "http://opencode.local",
		StructuredOutputMode: "auto",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "POST /session/session-1/message":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					format, ok := body["format"].(map[string]any)
					if !ok || format["type"] != "json_schema" {
						t.Fatalf("format = %#v", body["format"])
					}
					return jsonResponse(200, `{"info":{"structured":{"ok":true}},"parts":[{"type":"tool","tool":"StructuredOutput","state":{"input":{"ok":true}}}]}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	mode, err := client.ProbeStructuredOutput(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if mode != "json_schema" {
		t.Fatalf("mode = %q", mode)
	}
	if client.StructuredOutputMode() != "json_schema" {
		t.Fatalf("client mode = %q", client.StructuredOutputMode())
	}
}

func TestOpenCodeProbeStructuredOutputErrorIncludesRawResponse(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:              "http://opencode.local",
		StructuredOutputMode: "auto",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "POST /session/session-1/message":
					return jsonResponse(200, `{"ok":false,"reason":"schema ignored"}`), nil
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	_, err := client.ProbeStructuredOutput(context.Background())
	if err == nil {
		t.Fatal("expected probe error")
	}
	if !bytes.Contains([]byte(err.Error()), []byte(`{"ok":false,"reason":"schema ignored"}`)) {
		t.Fatalf("error missing raw response: %v", err)
	}
}

func TestOpenCodeReplyPermission(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.Method != "POST" || req.URL.Path != "/permission/perm-1/reply" {
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				}
				var body map[string]any
				if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
					t.Fatal(err)
				}
				if body["response"] != "always" {
					t.Fatalf("body = %#v", body)
				}
				return jsonResponse(200, `{"ok":true}`), nil
			}),
		},
	})

	if err := client.ReplyPermission(context.Background(), "perm-1", "always"); err != nil {
		t.Fatal(err)
	}
}

func TestParsePermissionEvent(t *testing.T) {
	raw := map[string]any{
		"type": "permission.asked",
		"properties": map[string]any{
			"id":         "perm-1",
			"sessionID":  "session-1",
			"permission": "edit",
			"patterns":   []any{"*.go"},
			"metadata":   map[string]any{"file": "main.go"},
		},
	}

	request, ok := ParsePermissionEvent(raw)
	if !ok {
		t.Fatal("expected permission event")
	}
	if request.ID != "perm-1" || request.SessionID != "session-1" || request.Permission != "edit" {
		t.Fatalf("request = %#v", request)
	}
	if len(request.Patterns) != 1 || request.Patterns[0] != "*.go" {
		t.Fatalf("patterns = %#v", request.Patterns)
	}
}

func TestOpenCodePollPermissionsUpdatesStatus(t *testing.T) {
	state := status.New()
	replyWhenAsked(t, state, "reject")
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.Method == "GET" && req.URL.Path == "/permission" {
					return jsonResponse(200, `[{"id":"perm-1","sessionID":"session-1","permission":"edit"}]`), nil
				}
				if req.Method == "POST" && req.URL.Path == "/permission/perm-1/reply" {
					return jsonResponse(200, `{"ok":true}`), nil
				}
				t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				return nil, nil
			}),
		},
	})

	if err := client.PollPermissionsOnce(context.Background(), "session-1", state, map[string]bool{}); err != nil {
		t.Fatal(err)
	}
	if state.Snapshot().PermissionRequest != nil {
		t.Fatal("permission should be cleared after reply")
	}
}

func replyWhenAsked(t *testing.T, state *status.Status, reply string) {
	t.Helper()
	go func() {
		deadline := time.After(time.Second)
		ticker := time.NewTicker(10 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-deadline:
				return
			case <-ticker.C:
				if state.Snapshot().PermissionRequest != nil {
					state.SetPermissionReply(reply)
					return
				}
			}
		}
	}()
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func jsonResponse(status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Body:       io.NopCloser(bytes.NewBufferString(body)),
		Header:     make(http.Header),
	}
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
