package specs

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.yaml.in/yaml/v4"
)

type AuditSpec struct {
	Name       string `yaml:"name"`
	UserPrompt string `yaml:"user_prompt"`
	Path       string `yaml:"-"`
}

func (s AuditSpec) SystemPrompt() string {
	displayName := strings.ReplaceAll(s.Name, "_", " ")
	return fmt.Sprintf(`你是一个代码安全审计专家，专门进行 %s 类型的漏洞审计。

## 任务
从公共 system prompt 中指定的入口函数开始，基于公共上下文中的 Function Skill、Code Map 和项目源码，判断当前入口函数是否存在 %s 安全问题。

## 通用审计要求
1. 只关注公共 system prompt 中指定入口函数相关的数据流、控制流和代码路径。
2. 必须从外部输入如何到达敏感操作、状态变更或安全决策开始分析。
3. 不要全局搜索危险函数、关键词或模式后直接下结论；必须证明其与当前入口函数有关。
4. 如果同一漏洞类型下存在多个独立 source/sink、控制流或利用条件，必须在 findings 数组中逐条输出。
5. 如果无法证明安全影响，应返回低置信度或无漏洞，不要编造问题。

## 类型标识
- 当前漏洞类型：%s
- findings 中的具体问题标题应写清楚风险点、sink 或失败的安全条件。`, displayName, displayName, s.Name)
}

func LoadFile(path string) (AuditSpec, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return AuditSpec{}, err
	}

	var spec AuditSpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return AuditSpec{}, fmt.Errorf("parse audit spec %s: %w", path, err)
	}
	spec.Path = path
	if spec.Name == "" {
		return AuditSpec{}, fmt.Errorf("audit spec missing name: %s", path)
	}
	if spec.UserPrompt == "" {
		return AuditSpec{}, fmt.Errorf("audit spec missing user_prompt: %s", path)
	}
	return spec, nil
}

func LoadDir(dir string) (map[string]AuditSpec, error) {
	matches, err := filepath.Glob(filepath.Join(dir, "*.yaml"))
	if err != nil {
		return nil, err
	}
	result := make(map[string]AuditSpec, len(matches))
	for _, path := range matches {
		spec, err := LoadFile(path)
		if err != nil {
			return nil, err
		}
		result[spec.Name] = spec
	}
	return result, nil
}
