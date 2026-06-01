package scanner

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"tsj-audit/internal/models"
)

func ValidateEntrySources(scanPath, entryPath, attackSurfaceSkill string) error {
	count := 0
	for _, value := range []string{scanPath, entryPath, attackSurfaceSkill} {
		if value != "" {
			count++
		}
	}
	if count != 1 {
		return fmt.Errorf("must specify exactly one of --scan, --entry, or --attack-surface-skill")
	}
	return nil
}

func LoadEntrySpecs(path string) ([]models.EntrySpec, error) {
	if filepath.Ext(path) != ".json" {
		return nil, fmt.Errorf("--entry only accepts JSON files: %s", path)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var entries []models.EntrySpec
	if err := json.Unmarshal(data, &entries); err != nil {
		return nil, err
	}
	return entries, nil
}
