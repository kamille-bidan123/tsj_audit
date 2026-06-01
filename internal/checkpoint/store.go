package checkpoint

import (
	"encoding/json"
	"os"
	"path/filepath"
	"unicode"

	"tsj-audit/internal/models"
)

type Store struct {
	OutputDir string
}

func (s Store) Save(result models.TraceResult) error {
	path := s.checkpointFile(result.FunctionInfo.FuncName)
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func (s Store) Load(funcName string) (models.TraceResult, bool, error) {
	path := s.checkpointFile(funcName)
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
		results[result.FunctionInfo.FuncName] = result
	}
	return results, nil
}

func (s Store) checkpointFile(funcName string) string {
	return filepath.Join(s.OutputDir, "checkpoints", safeName(funcName)+".json")
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
