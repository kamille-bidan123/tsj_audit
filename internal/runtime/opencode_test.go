package runtime

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
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
					var body map[string]string
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					if !strings.HasPrefix(body["title"], "tsj-audit ") {
						t.Fatalf("session body = %#v", body)
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
			case "GET /question":
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

func TestOpenCodeRunJSONCleansSessionAfterContextDeadline(t *testing.T) {
	deleted := make(chan struct{})
	client := NewOpenCode("http://opencode.local", &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			switch req.Method + " " + req.URL.Path {
			case "POST /session":
				return jsonResponse(200, `{"id":"session-1"}`), nil
			case "POST /session/session-1/message":
				<-req.Context().Done()
				return nil, req.Context().Err()
			case "DELETE /session/session-1":
				close(deleted)
				return jsonResponse(200, `{}`), nil
			default:
				t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				return nil, nil
			}
		}),
	})

	ctx, cancel := context.WithTimeout(context.Background(), time.Millisecond)
	defer cancel()
	if _, _, err := client.RunJSON(ctx, RunJSONRequest{StageName: "Trace", UserPrompt: "hello"}); err == nil {
		t.Fatal("expected context deadline")
	}
	select {
	case <-deleted:
	case <-time.After(time.Second):
		t.Fatal("session was not deleted after context deadline")
	}
}

func TestOpenCodeRunJSONRetriesMessageTimeoutWithNewSession(t *testing.T) {
	var calls []string
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:        "http://opencode.local",
		RequestRetries: 1,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				call := req.Method + " " + req.URL.Path
				calls = append(calls, call)
				switch call {
				case "POST /session":
					if countCalls(calls, "POST /session") == 1 {
						return jsonResponse(200, `{"id":"session-1"}`), nil
					}
					return jsonResponse(200, `{"id":"session-2"}`), nil
				case "POST /session/session-1/message":
					return nil, timeoutError{message: "context deadline exceeded"}
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				case "POST /session/session-2/message":
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-2":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s", call)
					return nil, nil
				}
			}),
		},
	})

	raw, _, err := client.RunJSON(context.Background(), RunJSONRequest{StageName: "Trace", UserPrompt: "hello"})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"assistant":"ok"}` {
		t.Fatalf("raw = %s", raw)
	}
	if countCalls(calls, "POST /session") != 2 {
		t.Fatalf("calls = %#v", calls)
	}
}

func TestOpenCodeRunJSONPausesTimeoutWhilePermissionIsPending(t *testing.T) {
	state := status.New()
	go func() {
		deadline := time.After(time.Second)
		ticker := time.NewTicker(10 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-deadline:
				return
			case <-ticker.C:
				snapshot := state.Snapshot()
				if len(snapshot.PermissionRequests) == 0 {
					continue
				}
				time.Sleep(120 * time.Millisecond)
				state.SetPermissionReply(snapshot.PermissionRequests[0].ID, "once")
				return
			}
		}
	}()
	replied := make(chan struct{})
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:        "http://opencode.local",
		RequestTimeout: 50 * time.Millisecond,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /permission":
					return jsonResponse(200, `[{"id":"perm-1","sessionID":"session-1","permission":"bash"}]`), nil
				case "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /permission/perm-1/reply":
					close(replied)
					return jsonResponse(200, `true`), nil
				case "POST /session/session-1/message":
					select {
					case <-replied:
						return jsonResponse(200, `{"assistant":"ok"}`), nil
					case <-req.Context().Done():
						return nil, req.Context().Err()
					}
				case "DELETE /session/session-1":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	raw, _, err := client.RunJSON(context.Background(), RunJSONRequest{
		StageName:  "Trace",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"assistant":"ok"}` {
		t.Fatalf("raw = %s", raw)
	}
}

func TestOpenCodeRunJSONTimesOutAfterActiveTimeBudget(t *testing.T) {
	state := status.New()
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:        "http://opencode.local",
		RequestRetries: 0,
		RequestTimeout: 30 * time.Millisecond,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /permission":
					return jsonResponse(200, `[]`), nil
				case "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /session/session-1/message":
					<-req.Context().Done()
					return nil, req.Context().Err()
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
	if err == nil {
		t.Fatal("expected timeout")
	}
	if !isRetryableTimeout(context.Background(), err) {
		t.Fatalf("expected retryable timeout, got %T %v", err, err)
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
				case "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /permission/perm-1/reply":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					if body["reply"] != "reject" {
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
				case "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /permission/perm-1/reply":
					var body map[string]any
					if err := json.NewDecoder(req.Body).Decode(&body); err != nil {
						t.Fatal(err)
					}
					if body["reply"] != "once" {
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

func TestOpenCodeRunJSONRejectsQuestionsDuringSession(t *testing.T) {
	state := status.New()
	rejected := make(chan struct{})
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /permission":
					return jsonResponse(200, `[]`), nil
				case "GET /question":
					return jsonResponse(200, `[{"id":"que-1","sessionID":"session-1","questions":[{"header":"Need context","question":"What is strMsg?"}]}]`), nil
				case "POST /question/que-1/reject":
					close(rejected)
					return jsonResponse(200, `true`), nil
				case "POST /session/session-1/message":
					select {
					case <-rejected:
					case <-time.After(time.Second):
						t.Fatal("question poll did not reject before message")
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
		StageName:  "Audit",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(state.Snapshot().Logs, "\n"), "[opencode:question] rejected id=que-1") {
		t.Fatalf("question reject log missing: %#v", state.Snapshot().Logs)
	}
}

func TestOpenCodeRunJSONRejectsQuestionEventStream(t *testing.T) {
	state := status.New()
	rejected := make(chan struct{})
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:           "http://opencode.local",
		EnableEventStream: true,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					return jsonResponse(200, `{"id":"session-1"}`), nil
				case "GET /event":
					return jsonResponse(200, "data: {\"type\":\"question.asked\",\"properties\":{\"id\":\"que-1\",\"sessionID\":\"session-1\",\"questions\":[{\"header\":\"Need context\",\"question\":\"What should I assume?\"}]}}\n\n"), nil
				case "GET /permission", "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /question/que-1/reject":
					close(rejected)
					return jsonResponse(200, `true`), nil
				case "POST /session/session-1/message":
					select {
					case <-rejected:
					case <-time.After(time.Second):
						t.Fatal("event stream did not reject question before message")
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
		StageName:  "Audit",
		UserPrompt: "hello",
		Status:     state,
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestOpenCodeToolEventLogsInputSummary(t *testing.T) {
	state := status.New()
	key := "Dice/DiceManager.h:71:CustomMsgApiHandler::handlePost"
	state.SetRuntimeForTask(key, "opencode", "session-1")
	client := NewOpenCodeWithOptions(OpenCodeOptions{BaseURL: "http://opencode.local"})
	client.eventSessions["session-1"] = state

	client.handleEvent(context.Background(), map[string]any{
		"type":      "tool",
		"sessionID": "session-1",
		"messageID": "message-1",
		"callID":    "call-1",
		"tool":      "read",
		"state": map[string]any{
			"status": "completed",
			"input": map[string]any{
				"filePath": "Dice/DiceManager.h",
				"offset":   float64(71),
				"limit":    float64(80),
			},
			"title": "Dice/DiceManager.h",
		},
	})

	logs := strings.Join(state.Snapshot().Logs, "\n")
	for _, needle := range []string{
		"tool=read",
		"call=call-1",
		"detail=Dice/DiceManager.h",
		"input=filePath=Dice/DiceManager.h offset=71 limit=80",
	} {
		if !strings.Contains(logs, needle) {
			t.Fatalf("logs missing %q:\n%s", needle, logs)
		}
	}
}

func TestOpenCodeToolEventLogsEachStatusOnce(t *testing.T) {
	state := status.New()
	key := "Dice/DiceManager.h:71:CustomMsgApiHandler::handlePost"
	state.SetRuntimeForTask(key, "opencode", "session-1")
	client := NewOpenCodeWithOptions(OpenCodeOptions{BaseURL: "http://opencode.local"})
	client.eventSessions["session-1"] = state
	event := map[string]any{
		"type":      "tool",
		"sessionID": "session-1",
		"messageID": "message-1",
		"callID":    "call-1",
		"tool":      "grep",
		"state": map[string]any{
			"status": "completed",
			"input":  map[string]any{"pattern": "mg_modify_passwords_file"},
			"title":  "mg_modify_passwords_file",
		},
	}

	client.handleEvent(context.Background(), event)
	client.handleEvent(context.Background(), event)

	logs := state.Snapshot().Logs
	var count int
	for _, line := range logs {
		if strings.Contains(line, "tool=grep") && strings.Contains(line, "status=completed") {
			count++
		}
	}
	if count != 1 {
		t.Fatalf("completed grep log count = %d, logs = %#v", count, logs)
	}
}

func TestOpenCodeEventStreamIsSharedAcrossSessions(t *testing.T) {
	state := status.New()
	eventRequests := 0
	eventSeen := make(chan struct{})
	sessionCreates := 0
	var eventWriter *io.PipeWriter
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL:           "http://opencode.local",
		EnableEventStream: true,
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "POST /session":
					sessionCreates++
					return jsonResponse(200, fmt.Sprintf(`{"id":"session-%d"}`, sessionCreates)), nil
				case "GET /event":
					eventRequests++
					if eventRequests == 1 {
						close(eventSeen)
					}
					reader, writer := io.Pipe()
					eventWriter = writer
					return &http.Response{
						StatusCode: 200,
						Body:       reader,
						Header:     make(http.Header),
					}, nil
				case "GET /permission":
					return jsonResponse(200, `[]`), nil
				case "GET /question":
					return jsonResponse(200, `[]`), nil
				case "POST /session/session-1/message", "POST /session/session-2/message":
					return jsonResponse(200, `{"assistant":"ok"}`), nil
				case "DELETE /session/session-1", "DELETE /session/session-2":
					return jsonResponse(200, `{}`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	for i := 0; i < 2; i++ {
		if _, _, err := client.RunJSON(context.Background(), RunJSONRequest{
			StageName:  "Trace",
			UserPrompt: "hello",
			Status:     state,
		}); err != nil {
			t.Fatal(err)
		}
	}
	select {
	case <-eventSeen:
	case <-time.After(time.Second):
		t.Fatal("event listener did not start")
	}
	if eventWriter != nil {
		_ = eventWriter.Close()
	}
	if eventRequests != 1 {
		t.Fatalf("event requests = %d, want 1", eventRequests)
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

func TestExtractOpenCodeStructuredPayloadUnwrapsInputEnvelope(t *testing.T) {
	raw := json.RawMessage(`{
		"info": {
			"structured": {
				"input": {
					"is_vulnerable": false,
					"confidence": "high",
					"description": "no command injection"
				}
			}
		}
	}`)

	payload := extractOpenCodeStructuredPayload(raw)
	var output map[string]any
	if err := json.Unmarshal(payload, &output); err != nil {
		t.Fatal(err)
	}
	if _, ok := output["input"]; ok {
		t.Fatalf("payload still wrapped in input: %s", string(payload))
	}
	if output["confidence"] != "high" || output["description"] != "no command injection" {
		t.Fatalf("payload = %#v", output)
	}

	toolRaw := json.RawMessage(`{
		"parts": [
			{
				"type": "tool",
				"tool": "StructuredOutput",
				"state": {
					"input": {
						"input": {
							"is_vulnerable": false,
							"confidence": "low",
							"description": "none"
						}
					}
				}
			}
		]
	}`)
	payload = extractOpenCodeStructuredPayload(toolRaw)
	if err := json.Unmarshal(payload, &output); err != nil {
		t.Fatal(err)
	}
	if _, ok := output["input"]; ok {
		t.Fatalf("tool payload still wrapped in input: %s", string(payload))
	}
	if output["confidence"] != "low" || output["description"] != "none" {
		t.Fatalf("tool payload = %#v", output)
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
				if body["reply"] != "always" {
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

func TestOpenCodeRejectQuestion(t *testing.T) {
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				if req.Method != "POST" || req.URL.Path != "/question/que-1/reject" {
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
				}
				return jsonResponse(200, `true`), nil
			}),
		},
	})

	if err := client.RejectQuestion(context.Background(), "que-1"); err != nil {
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

func TestParseQuestionEvent(t *testing.T) {
	raw := map[string]any{
		"type": "question.asked",
		"properties": map[string]any{
			"id":        "que-1",
			"sessionID": "session-1",
			"questions": []any{
				map[string]any{"header": "Need context", "question": "What is strMsg?"},
			},
		},
	}

	request, ok := ParseQuestionEvent(raw)
	if !ok {
		t.Fatal("expected question event")
	}
	if request.ID != "que-1" || request.SessionID != "session-1" {
		t.Fatalf("request = %#v", request)
	}
	if summarizeQuestionRequest(request) != "Need context: What is strMsg?" {
		t.Fatalf("summary = %q", summarizeQuestionRequest(request))
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

func TestOpenCodePollQuestionsRejectsPendingQuestion(t *testing.T) {
	state := status.New()
	seen := map[string]bool{}
	rejected := false
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "GET /question":
					return jsonResponse(200, `[{"id":"que-1","sessionID":"session-1","questions":[{"header":"Need context","question":"What is strMsg?"}]}]`), nil
				case "POST /question/que-1/reject":
					rejected = true
					return jsonResponse(200, `true`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	if err := client.PollQuestionsOnce(context.Background(), "session-1", state, seen); err != nil {
		t.Fatal(err)
	}
	if !rejected || !seen["que-1"] {
		t.Fatalf("rejected=%v seen=%#v", rejected, seen)
	}
}

func TestOpenCodePollPermissionsRetriesWhenReplyFails(t *testing.T) {
	state := status.New()
	seen := map[string]bool{}
	replyAttempts := 0
	replyWhenAsked(t, state, "always")
	client := NewOpenCodeWithOptions(OpenCodeOptions{
		BaseURL: "http://opencode.local",
		HTTPClient: &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				switch req.Method + " " + req.URL.Path {
				case "GET /permission":
					return jsonResponse(200, `[{"id":"perm-1","sessionID":"session-1","permission":"bash"}]`), nil
				case "POST /permission/perm-1/reply":
					replyAttempts++
					if replyAttempts == 1 {
						return jsonResponse(400, `{"name":"BadRequest"}`), nil
					}
					return jsonResponse(200, `true`), nil
				default:
					t.Fatalf("unexpected request: %s %s", req.Method, req.URL.Path)
					return nil, nil
				}
			}),
		},
	})

	if err := client.PollPermissionsOnce(context.Background(), "session-1", state, seen); err == nil {
		t.Fatal("expected first reply to fail")
	}
	if seen["perm-1"] {
		t.Fatal("failed reply should not mark permission as seen")
	}
	replyWhenAsked(t, state, "always")
	if err := client.PollPermissionsOnce(context.Background(), "session-1", state, seen); err != nil {
		t.Fatal(err)
	}
	if !seen["perm-1"] {
		t.Fatal("successful reply should mark permission as seen")
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
				snapshot := state.Snapshot()
				if len(snapshot.PermissionRequests) > 0 {
					state.SetPermissionReply(snapshot.PermissionRequests[0].ID, reply)
					return
				}
				if snapshot.PermissionRequest != nil {
					state.SetPermissionReply(snapshot.PermissionRequest.ID, reply)
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

type timeoutError struct {
	message string
}

func (e timeoutError) Error() string {
	return e.message
}

func (e timeoutError) Timeout() bool {
	return true
}

func (e timeoutError) Temporary() bool {
	return true
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

func countCalls(calls []string, needle string) int {
	count := 0
	for _, call := range calls {
		if call == needle {
			count++
		}
	}
	return count
}
