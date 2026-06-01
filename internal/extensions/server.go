package extensions

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"go.yaml.in/yaml/v4"
)

var idPattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

type auditSpecYAML struct {
	Name       string `yaml:"name"`
	UserPrompt string `yaml:"user_prompt"`
}

type skillFrontmatterYAML struct {
	Name               string   `yaml:"name"`
	Description        string   `yaml:"description,omitempty"`
	RequiredAuditTypes []string `yaml:"required_audit_types,omitempty"`
}

type Server struct {
	Root string
}

type apiError struct {
	status  int
	message string
}

func (e apiError) Error() string {
	return e.message
}

func NewServer(root string) Server {
	return Server{Root: root}
}

func (s Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", s.handle)
	return mux
}

func (s Server) handle(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()
	path := r.URL.Path
	var response any
	var status int
	var err error
	switch {
	case r.Method == http.MethodGet && (path == "/" || path == "/index.html"):
		s.serveFile(w)
		return
	case r.Method == http.MethodGet && path == "/api/state":
		response, err = s.state()
	case r.Method == http.MethodGet && path == "/api/audit-specs":
		items, listErr := s.listAuditSpecs()
		response, err = map[string]any{"items": items}, listErr
	case r.Method == http.MethodPost && path == "/api/audit-specs":
		body, readErr := readBody(r)
		if readErr != nil {
			err = readErr
			break
		}
		response, status, err = s.saveAuditSpec(stringValue(body["id"], stringValue(body["name"], "")), body, true)
	case strings.HasPrefix(path, "/api/audit-specs/"):
		response, status, err = s.handleAuditSpecItem(r, strings.TrimPrefix(path, "/api/audit-specs/"))
	case r.Method == http.MethodGet && path == "/api/attack-surface-skills":
		items, listErr := s.listAttackSurfaceSkills()
		response, err = map[string]any{"items": items}, listErr
	case r.Method == http.MethodPost && path == "/api/attack-surface-skills":
		body, readErr := readBody(r)
		if readErr != nil {
			err = readErr
			break
		}
		response, status, err = s.saveAttackSurfaceSkill(stringValue(body["id"], stringValue(body["name"], "")), body, true)
	case strings.HasPrefix(path, "/api/attack-surface-skills/"):
		response, status, err = s.handleSkillItem(r, strings.TrimPrefix(path, "/api/attack-surface-skills/"), true)
	case r.Method == http.MethodGet && path == "/api/skills":
		items, listErr := s.listSkills()
		response, err = map[string]any{"items": items}, listErr
	case r.Method == http.MethodPost && path == "/api/skills":
		body, readErr := readBody(r)
		if readErr != nil {
			err = readErr
			break
		}
		response, status, err = s.saveSkill(stringValue(body["id"], stringValue(body["name"], "")), body, true)
	case strings.HasPrefix(path, "/api/skills/"):
		response, status, err = s.handleSkillItem(r, strings.TrimPrefix(path, "/api/skills/"), false)
	default:
		err = apiError{status: http.StatusNotFound, message: "未知路径: " + path}
	}
	if err != nil {
		s.writeError(w, err)
		return
	}
	if status == 0 {
		status = http.StatusOK
	}
	writeJSON(w, response, status)
}

func (s Server) serveFile(w http.ResponseWriter) {
	data, err := os.ReadFile(filepath.Join(s.Root, "web", "extensions_manager.html"))
	if err != nil {
		s.writeError(w, apiError{status: http.StatusNotFound, message: err.Error()})
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

func (s Server) state() (map[string]any, error) {
	auditSpecs, err := s.listAuditSpecs()
	if err != nil {
		return nil, err
	}
	attackSurfaceSkills, err := s.listAttackSurfaceSkills()
	if err != nil {
		return nil, err
	}
	skills, err := s.listSkills()
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"audit_specs":           auditSpecs,
		"attack_surface_skills": attackSurfaceSkills,
		"skills":                skills,
	}, nil
}

func (s Server) listAuditSpecs() ([]map[string]any, error) {
	paths, err := filepath.Glob(filepath.Join(s.Root, "audit_specs", "*.yaml"))
	if err != nil {
		return nil, err
	}
	sort.Strings(paths)
	items := []map[string]any{}
	for _, path := range paths {
		spec := parseAuditSpecFile(path)
		id := strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
		items = append(items, map[string]any{
			"id":          id,
			"name":        firstNonEmpty(spec["name"], id),
			"user_prompt": spec["user_prompt"],
			"path":        slashRel(s.Root, path),
		})
	}
	return items, nil
}

func (s Server) saveAuditSpec(id string, data map[string]any, create bool) (map[string]any, int, error) {
	id, err := validateID(id, "audit spec id")
	if err != nil {
		return nil, 0, err
	}
	name, err := validateID(stringValue(data["name"], id), "audit type name")
	if err != nil {
		return nil, 0, err
	}
	userPrompt := strings.TrimSpace(stringValue(data["user_prompt"], ""))
	if userPrompt == "" {
		return nil, 0, apiError{status: http.StatusBadRequest, message: "user_prompt 不能为空"}
	}
	path := filepath.Join(s.Root, "audit_specs", id+".yaml")
	if create && exists(path) {
		return nil, 0, apiError{status: http.StatusConflict, message: "audit spec 已存在: " + id}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return nil, 0, err
	}
	content, err := marshalAuditSpec(auditSpecYAML{Name: name, UserPrompt: userPrompt})
	if err != nil {
		return nil, 0, err
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		return nil, 0, err
	}
	return map[string]any{"id": id, "name": name, "user_prompt": userPrompt, "path": slashRel(s.Root, path)}, statusForCreate(create), nil
}

func (s Server) handleAuditSpecItem(r *http.Request, id string) (map[string]any, int, error) {
	switch r.Method {
	case http.MethodPut:
		body, err := readBody(r)
		if err != nil {
			return nil, 0, err
		}
		return s.saveAuditSpec(id, body, false)
	case http.MethodDelete:
		return s.deleteFile(filepath.Join(s.Root, "audit_specs", id+".yaml"), id, "audit spec")
	default:
		return nil, 0, apiError{status: http.StatusNotFound, message: "未知路径: " + r.URL.Path}
	}
}

func (s Server) listSkills() ([]map[string]any, error) {
	return s.listSkillDir(filepath.Join(s.Root, "skills"), false)
}

func (s Server) listAttackSurfaceSkills() ([]map[string]any, error) {
	return s.listSkillDir(filepath.Join(s.Root, "skills", "attack_surface"), true)
}

func (s Server) listSkillDir(dir string, attackSurface bool) ([]map[string]any, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return []map[string]any{}, nil
		}
		return nil, err
	}
	items := []map[string]any{}
	for _, entry := range entries {
		if !entry.IsDir() || (!attackSurface && entry.Name() == "attack_surface") {
			continue
		}
		path := filepath.Join(dir, entry.Name(), "SKILL.md")
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		meta, body := splitFrontmatter(string(data))
		item := map[string]any{
			"id":          entry.Name(),
			"name":        firstNonEmpty(stringValue(meta["name"], ""), entry.Name()),
			"description": stringValue(meta["description"], ""),
			"metadata":    meta,
			"body":        body,
			"path":        slashRel(s.Root, path),
		}
		if attackSurface {
			item["required_audit_types"] = stringList(meta["required_audit_types"])
			for key, value := range splitAttackSurfaceBody(body) {
				item[key] = value
			}
		}
		items = append(items, item)
	}
	return items, nil
}

func (s Server) saveSkill(id string, data map[string]any, create bool) (map[string]any, int, error) {
	id, err := validateID(id, "skill id")
	if err != nil {
		return nil, 0, err
	}
	name := strings.TrimSpace(stringValue(data["name"], id))
	body := strings.TrimSpace(stringValue(data["body"], ""))
	if name == "" || body == "" {
		return nil, 0, apiError{status: http.StatusBadRequest, message: "skill name 和正文不能为空"}
	}
	path := filepath.Join(s.Root, "skills", id, "SKILL.md")
	if create && exists(path) {
		return nil, 0, apiError{status: http.StatusConflict, message: "skill 已存在: " + id}
	}
	meta := map[string]any{"name": name, "description": strings.TrimSpace(stringValue(data["description"], ""))}
	if err := writeSkill(path, meta, body); err != nil {
		return nil, 0, err
	}
	return map[string]any{"id": id, "name": name, "description": meta["description"], "metadata": meta, "body": body, "path": slashRel(s.Root, path)}, statusForCreate(create), nil
}

func (s Server) saveAttackSurfaceSkill(id string, data map[string]any, create bool) (map[string]any, int, error) {
	id, err := validateID(id, "attack surface skill id")
	if err != nil {
		return nil, 0, err
	}
	name := strings.TrimSpace(stringValue(data["name"], id))
	required := dedupeIDs(stringList(data["required_audit_types"]))
	for _, field := range []string{"discovery_knowledge", "input_knowledge", "poc_knowledge"} {
		if strings.TrimSpace(stringValue(data[field], "")) == "" {
			return nil, 0, apiError{status: http.StatusBadRequest, message: field + " 不能为空"}
		}
	}
	body := renderAttackSurfaceBody(name, data)
	meta := map[string]any{
		"name":                 name,
		"description":          strings.TrimSpace(stringValue(data["description"], "")),
		"required_audit_types": required,
	}
	path := filepath.Join(s.Root, "skills", "attack_surface", id, "SKILL.md")
	if create && exists(path) {
		return nil, 0, apiError{status: http.StatusConflict, message: "attack surface skill 已存在: " + id}
	}
	if err := writeSkill(path, meta, body); err != nil {
		return nil, 0, err
	}
	item := map[string]any{"id": id, "name": name, "description": meta["description"], "required_audit_types": required, "metadata": meta, "body": body, "path": slashRel(s.Root, path)}
	for key, value := range splitAttackSurfaceBody(body) {
		item[key] = value
	}
	return item, statusForCreate(create), nil
}

func (s Server) handleSkillItem(r *http.Request, id string, attackSurface bool) (map[string]any, int, error) {
	switch r.Method {
	case http.MethodPut:
		body, err := readBody(r)
		if err != nil {
			return nil, 0, err
		}
		if attackSurface {
			return s.saveAttackSurfaceSkill(id, body, false)
		}
		return s.saveSkill(id, body, false)
	case http.MethodDelete:
		dir := filepath.Join(s.Root, "skills", id)
		if attackSurface {
			dir = filepath.Join(s.Root, "skills", "attack_surface", id)
		}
		return s.deleteSkillDir(dir, id)
	default:
		return nil, 0, apiError{status: http.StatusNotFound, message: "未知路径: " + r.URL.Path}
	}
}

func (s Server) deleteFile(path string, id string, label string) (map[string]any, int, error) {
	if _, err := validateID(id, label+" id"); err != nil {
		return nil, 0, err
	}
	if !exists(path) {
		return nil, 0, apiError{status: http.StatusNotFound, message: label + " 不存在: " + id}
	}
	if err := os.Remove(path); err != nil {
		return nil, 0, err
	}
	return map[string]any{"deleted": id}, http.StatusOK, nil
}

func (s Server) deleteSkillDir(dir string, id string) (map[string]any, int, error) {
	if _, err := validateID(id, "skill id"); err != nil {
		return nil, 0, err
	}
	skillFile := filepath.Join(dir, "SKILL.md")
	if !exists(skillFile) {
		return nil, 0, apiError{status: http.StatusNotFound, message: "skill 不存在: " + id}
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, 0, err
	}
	for _, entry := range entries {
		if entry.Name() != "SKILL.md" {
			return nil, 0, apiError{status: http.StatusConflict, message: "该 skill 包含子文件，请先手动处理"}
		}
	}
	if err := os.Remove(skillFile); err != nil {
		return nil, 0, err
	}
	if err := os.Remove(dir); err != nil {
		return nil, 0, err
	}
	return map[string]any{"deleted": id}, http.StatusOK, nil
}

func (s Server) writeError(w http.ResponseWriter, err error) {
	var api apiError
	if typed, ok := err.(apiError); ok {
		api = typed
	} else {
		api = apiError{status: http.StatusInternalServerError, message: err.Error()}
	}
	writeJSON(w, map[string]any{"error": api.message}, api.status)
}

func readBody(r *http.Request) (map[string]any, error) {
	var data map[string]any
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		return nil, apiError{status: http.StatusBadRequest, message: "请求 JSON 无效: " + err.Error()}
	}
	if data == nil {
		data = map[string]any{}
	}
	return data, nil
}

func writeJSON(w http.ResponseWriter, data any, status int) {
	payload, _ := json.MarshalIndent(data, "", "  ")
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write(payload)
}

func validateID(value string, label string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" || !idPattern.MatchString(value) {
		return "", apiError{status: http.StatusBadRequest, message: label + " 只能包含字母、数字、下划线和短横线"}
	}
	return value, nil
}

func parseAuditSpecFile(path string) map[string]string {
	result := map[string]string{}
	data, err := os.ReadFile(path)
	if err != nil {
		return result
	}
	var spec auditSpecYAML
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return result
	}
	result["name"] = spec.Name
	result["user_prompt"] = spec.UserPrompt
	return result
}

func marshalAuditSpec(spec auditSpecYAML) (string, error) {
	root := yaml.Node{Kind: yaml.MappingNode}
	root.Content = []*yaml.Node{
		{Kind: yaml.ScalarNode, Value: "name"},
		{Kind: yaml.ScalarNode, Value: spec.Name},
		{Kind: yaml.ScalarNode, Value: "user_prompt"},
		{Kind: yaml.ScalarNode, Value: spec.UserPrompt, Style: yaml.LiteralStyle},
	}
	data, err := yaml.Marshal(&root)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func splitFrontmatter(text string) (map[string]any, string) {
	meta := map[string]any{}
	if !strings.HasPrefix(text, "---\n") {
		return meta, text
	}
	rest := strings.TrimPrefix(text, "---\n")
	frontmatter, body, ok := strings.Cut(rest, "\n---")
	if !ok {
		return meta, text
	}
	if err := yaml.Unmarshal([]byte(frontmatter), &meta); err != nil {
		return map[string]any{}, text
	}
	return meta, strings.TrimSpace(strings.TrimPrefix(body, "\n"))
}

func writeSkill(path string, meta map[string]any, body string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte("---\n"+renderMeta(meta)+"---\n\n"+strings.TrimSpace(body)+"\n"), 0644)
}

func renderMeta(meta map[string]any) string {
	frontmatter := skillFrontmatterYAML{
		Name:               stringValue(meta["name"], ""),
		Description:        stringValue(meta["description"], ""),
		RequiredAuditTypes: stringList(meta["required_audit_types"]),
	}
	data, err := yaml.Marshal(frontmatter)
	if err != nil {
		return ""
	}
	return string(data)
}

func splitAttackSurfaceBody(body string) map[string]string {
	sections := map[string]string{"discovery_knowledge": "", "input_knowledge": "", "poc_knowledge": ""}
	headers := map[string]string{"## 攻击面发现知识": "discovery_knowledge", "## 外部输入知识": "input_knowledge", "## PoC 生成知识": "poc_knowledge"}
	current := ""
	var lines []string
	flush := func() {
		if current != "" {
			sections[current] = strings.TrimSpace(strings.Join(lines, "\n"))
		}
	}
	for _, line := range strings.Split(body, "\n") {
		if key, ok := headers[strings.TrimSpace(line)]; ok {
			flush()
			current = key
			lines = nil
			continue
		}
		if current != "" {
			lines = append(lines, line)
		}
	}
	flush()
	return sections
}

func renderAttackSurfaceBody(name string, data map[string]any) string {
	return fmt.Sprintf("# %s\n\n## 攻击面发现知识\n\n%s\n\n## 外部输入知识\n\n%s\n\n## PoC 生成知识\n\n%s\n",
		name,
		strings.TrimSpace(stringValue(data["discovery_knowledge"], "")),
		strings.TrimSpace(stringValue(data["input_knowledge"], "")),
		strings.TrimSpace(stringValue(data["poc_knowledge"], "")),
	)
}

func indentBlock(value string) string {
	lines := strings.Split(value, "\n")
	for i := range lines {
		lines[i] = "  " + lines[i]
	}
	return strings.Join(lines, "\n")
}

func stringValue(value any, fallback string) string {
	if text, ok := value.(string); ok {
		return text
	}
	return fallback
}

func stringList(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		var result []string
		for _, item := range typed {
			if text, ok := item.(string); ok {
				result = append(result, text)
			}
		}
		return result
	case string:
		var result []string
		for _, item := range strings.Split(typed, ",") {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				result = append(result, trimmed)
			}
		}
		return result
	default:
		return nil
	}
}

func dedupeIDs(values []string) []string {
	seen := map[string]bool{}
	var result []string
	for _, value := range values {
		valid, err := validateID(value, "audit type")
		if err == nil && !seen[valid] {
			seen[valid] = true
			result = append(result, valid)
		}
	}
	return result
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func slashRel(root string, path string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(rel)
}

func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func statusForCreate(create bool) int {
	if create {
		return http.StatusCreated
	}
	return http.StatusOK
}
