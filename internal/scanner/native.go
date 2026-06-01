package scanner

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"tsj-audit/internal/models"
)

var sourceExtensions = map[string]bool{
	".c": true, ".h": true, ".cc": true, ".hh": true,
	".cpp": true, ".hpp": true, ".cxx": true, ".hxx": true,
}

var skipDirs = map[string]bool{
	".git": true, ".svn": true, ".hg": true,
	"build": true, "out": true, "dist": true, "bin": true, "obj": true,
	"node_modules": true, "__pycache__": true, ".venv": true,
	"venv": true, "env": true, ".cache": true,
}

var (
	civetSetHandlerPattern = regexp.MustCompile(`(?s)mg_set_request_handler\s*\(\s*[^,]+,\s*["'][^"']+["']\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]`)
	civetMethodPattern     = regexp.MustCompile(`\b(handleGet|handlePost|handlePut|handleDelete|handlePatch|handleHead|handleOptions)\s*\(\s*CivetServer\s*\*\s*\w*\s*,\s*struct\s+mg_connection\s*\*\s*\w*\s*\)`)
	ioctlRegisteredPattern = regexp.MustCompile(`(?m)\.(?:unlocked_)?ioctl\s*=\s*([A-Za-z_][A-Za-z0-9_]*)`)
	ioctlFunctionPattern   = regexp.MustCompile(`(?m)(?:^|\n)\s*(?:static\s+)?(?:long|int)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{`)
	ioctlNameFragment      = regexp.MustCompile(`(?i)ioctl`)
)

func RunAttackSurfaceScan(skillName string, projectPath string) ([]models.EntrySpec, bool, error) {
	switch skillName {
	case "civetweb_audit":
		entries, err := scanCivetWeb(projectPath)
		return entries, true, err
	case "ioctl_audit":
		entries, err := scanIOCTL(projectPath)
		return entries, true, err
	default:
		return nil, false, nil
	}
}

func RunScan(ctx context.Context, scanPath string, projectPath string) ([]models.EntrySpec, error) {
	if skillName, ok := nativeSkillForScanPath(scanPath); ok {
		entries, _, err := RunAttackSurfaceScan(skillName, projectPath)
		return entries, err
	}
	return RunPythonScan(ctx, scanPath, projectPath)
}

func nativeSkillForScanPath(scanPath string) (string, bool) {
	clean := filepath.ToSlash(filepath.Clean(scanPath))
	base := filepath.Base(clean)
	switch {
	case strings.Contains(clean, "ioctl_audit/scripts/scan.py"), base == "scan_ioctl.py":
		return "ioctl_audit", true
	case strings.Contains(clean, "civetweb_audit/scripts/scan.py"), base == "scan.py":
		return "civetweb_audit", true
	default:
		return "", false
	}
}

func scanCivetWeb(projectPath string) ([]models.EntrySpec, error) {
	files, err := sourceFiles(projectPath)
	if err != nil {
		return nil, err
	}
	var entries []models.EntrySpec
	seen := map[string]bool{}
	for _, relPath := range files {
		content, err := os.ReadFile(filepath.Join(projectPath, relPath))
		if err != nil {
			return nil, err
		}
		text := string(content)
		for _, match := range civetSetHandlerPattern.FindAllStringSubmatchIndex(text, -1) {
			name := text[match[2]:match[3]]
			startLine := findFunctionStartLine(text, name)
			if startLine == 0 {
				startLine = lineAtOffset(text, match[0])
			}
			entries = appendUniqueEntry(entries, seen, name, relPath, startLine, "civetweb_audit")
		}
		for _, match := range civetMethodPattern.FindAllStringSubmatchIndex(text, -1) {
			name := text[match[2]:match[3]]
			startLine := lineAtOffset(text, match[0])
			entries = appendUniqueEntry(entries, seen, name, relPath, startLine, "civetweb_audit")
		}
	}
	return entries, nil
}

func scanIOCTL(projectPath string) ([]models.EntrySpec, error) {
	files, err := sourceFiles(projectPath)
	if err != nil {
		return nil, err
	}
	var entries []models.EntrySpec
	seen := map[string]bool{}
	for _, relPath := range files {
		content, err := os.ReadFile(filepath.Join(projectPath, relPath))
		if err != nil {
			return nil, err
		}
		text := string(content)
		registered := map[string]bool{}
		for _, match := range ioctlRegisteredPattern.FindAllStringSubmatch(text, -1) {
			registered[match[1]] = true
		}
		for _, match := range ioctlFunctionPattern.FindAllStringSubmatchIndex(text, -1) {
			name := text[match[2]:match[3]]
			params := text[match[4]:match[5]]
			if !registered[name] && !ioctlNameFragment.MatchString(name) && !looksLikeIOCTLParams(params) {
				continue
			}
			startLine := lineAtOffset(text, match[0])
			entries = appendUniqueEntry(entries, seen, name, relPath, startLine, "ioctl_audit")
		}
	}
	return entries, nil
}

func sourceFiles(projectPath string) ([]string, error) {
	var files []string
	err := filepath.WalkDir(projectPath, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			name := entry.Name()
			if name != "." && (skipDirs[name] || strings.HasPrefix(name, ".")) {
				return filepath.SkipDir
			}
			return nil
		}
		if !sourceExtensions[strings.ToLower(filepath.Ext(path))] {
			return nil
		}
		rel, err := filepath.Rel(projectPath, path)
		if err != nil {
			return err
		}
		files = append(files, filepath.ToSlash(rel))
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Strings(files)
	return files, nil
}

func appendUniqueEntry(entries []models.EntrySpec, seen map[string]bool, name string, path string, line int, skill string) []models.EntrySpec {
	key := fmt.Sprintf("%s\x00%s\x00%d", name, path, line)
	if seen[key] {
		return entries
	}
	seen[key] = true
	return append(entries, models.EntrySpec{
		FuncName:  name,
		FilePath:  path,
		StartLine: models.IntPtr(line),
		Skill:     models.StringPtr(skill),
	})
}

func findFunctionStartLine(content string, name string) int {
	pattern := regexp.MustCompile(`(?m)(?:^|\n)\s*(?:static\s+)?[A-Za-z_][A-Za-z0-9_\s\*]*\b` + regexp.QuoteMeta(name) + `\s*\(`)
	match := pattern.FindStringIndex(content)
	if match == nil {
		return 0
	}
	offset := match[0]
	if offset < len(content) && content[offset] == '\n' {
		offset++
	}
	return lineAtOffset(content, offset)
}

func lineAtOffset(content string, offset int) int {
	if offset < 0 {
		return 1
	}
	if offset > len(content) {
		offset = len(content)
	}
	return strings.Count(content[:offset], "\n") + 1
}

func looksLikeIOCTLParams(params string) bool {
	lower := strings.ToLower(params)
	return strings.Contains(lower, "cmd") && (strings.Contains(lower, "unsigned long") || strings.Contains(lower, "struct file"))
}
