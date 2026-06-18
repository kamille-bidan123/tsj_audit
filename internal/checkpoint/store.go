package checkpoint

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"unicode"

	"tsj-audit/internal/models"
)

type Store struct {
	OutputDir string
}

var functionLogMu sync.Mutex

type FunctionLogEntry struct {
	Time         string `json:"time"`
	EntryKey     string `json:"entry_key"`
	Stage        string `json:"stage,omitempty"`
	FunctionName string `json:"function_name,omitempty"`
	AuditType    string `json:"audit_type,omitempty"`
	SessionID    string `json:"session_id,omitempty"`
	Message      string `json:"message"`
}

type ConversationEntry struct {
	Time         string               `json:"time"`
	EntryKey     string               `json:"entry_key"`
	StageName    string               `json:"stage_name"`
	FunctionName string               `json:"function_name,omitempty"`
	SessionID    string               `json:"session_id,omitempty"`
	Request      ConversationRequest  `json:"request"`
	Response     ConversationResponse `json:"response"`
	Error        string               `json:"error,omitempty"`
}

type ConversationRequest struct {
	UserPrompt string          `json:"user_prompt"`
	Schema     json.RawMessage `json:"schema,omitempty"`
}

type ConversationResponse struct {
	Raw      json.RawMessage        `json:"raw,omitempty"`
	Payload  json.RawMessage        `json:"payload,omitempty"`
	Messages []ConversationMessage  `json:"messages,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

type ConversationMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

func (s Store) Save(result models.TraceResult) error {
	return s.SaveForKey(result.FunctionInfo.Key(), result)
}

func (s Store) SaveForKey(key string, result models.TraceResult) error {
	path := s.checkpointFile(key)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func (s Store) Load(key string) (models.TraceResult, bool, error) {
	path := s.checkpointFile(key)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return models.TraceResult{}, false, nil
		}
		return models.TraceResult{}, false, err
	}
	var result models.TraceResult
	if err := json.Unmarshal(data, &result); err != nil {
		return models.TraceResult{}, false, err
	}
	return result, true, nil
}

func (s Store) LoadAll() (map[string]models.TraceResult, error) {
	dir := filepath.Join(s.OutputDir, "checkpoints")
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]models.TraceResult{}, nil
		}
		return nil, err
	}

	results := map[string]models.TraceResult{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(dir, entry.Name()))
		if err != nil {
			return nil, err
		}
		var result models.TraceResult
		if err := json.Unmarshal(data, &result); err != nil {
			continue
		}
		results[result.FunctionInfo.Key()] = result
	}
	return results, nil
}

func (s Store) AppendFunctionLog(entry FunctionLogEntry) error {
	if entry.EntryKey == "" {
		return nil
	}
	path := filepath.Join(s.OutputDir, "checkpoints", "logs", safeName(entry.EntryKey)+".jsonl")
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	data, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	functionLogMu.Lock()
	defer functionLogMu.Unlock()
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	defer file.Close()
	_, err = file.Write(data)
	return err
}

func (s Store) SaveConversation(entry ConversationEntry) (string, error) {
	if entry.EntryKey == "" {
		return "", nil
	}
	normalizeConversationRawMessages(&entry)
	dir := filepath.Join(s.OutputDir, "checkpoints", "conversations", safeName(entry.EntryKey))
	if err := os.MkdirAll(dir, 0755); err != nil {
		return "", err
	}
	name := safeName(entry.StageName)
	if name == "" {
		name = "conversation"
	}
	prefix := safeName(entry.Time)
	if prefix == "" {
		prefix = "conversation"
	}
	path := filepath.Join(dir, prefix+"_"+name+".json")
	data, err := json.MarshalIndent(entry, "", "  ")
	if err != nil {
		return "", err
	}
	return path, os.WriteFile(path, data, 0644)
}

func normalizeConversationRawMessages(entry *ConversationEntry) {
	entry.Request.Schema = normalizeRawMessage(entry.Request.Schema)
	entry.Response.Raw = normalizeRawMessage(entry.Response.Raw)
	entry.Response.Payload = normalizeRawMessage(entry.Response.Payload)
}

func normalizeRawMessage(value json.RawMessage) json.RawMessage {
	if len(bytes.TrimSpace(value)) == 0 {
		return nil
	}
	return value
}

func (s Store) checkpointFile(key string) string {
	return filepath.Join(s.OutputDir, "checkpoints", safeName(key)+".json")
}

func safeName(value string) string {
	runes := make([]rune, 0, len(value))
	for _, char := range value {
		if unicode.IsLetter(char) || unicode.IsDigit(char) || char == '_' || char == '-' {
			runes = append(runes, char)
		} else {
			runes = append(runes, '_')
		}
	}
	return string(runes)
}
