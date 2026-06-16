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
从公共 system prompt 中指定的入口函数开始，基于公共上下文中的 Function Skill、trace code_map 函数级上下文和项目源码，判断当前入口函数是否存在 %s 安全问题。

## 通用审计要求
1. 只关注公共 system prompt 中指定入口函数相关的数据流、控制流和代码路径。
2. 必须从外部输入如何到达敏感操作、状态变更或安全决策开始分析。
3. 不要全局搜索危险函数、关键词或模式后直接下结论；必须证明其与当前入口函数有关。
4. 如果同一漏洞类型下存在多个独立 source/sink、数据流、控制流或利用条件，必须在 findings 数组中逐条输出。
5. 如果无法证明安全影响，应返回低置信度或无漏洞，不要编造问题。
6. 公共上下文中的 trace code_map 是函数级上下文索引，可以作为审计依据复用。
7. 每个 finding 必须以一条具体污点/数据流为单位表达证据，不要把整个函数或整段调用图当作一个 finding。
8. primary_location 指向主要修复位置；data_flows[].steps[] 只描述该 finding 的 source -> propagation/condition/validator/sanitizer -> sink 路径。
9. data_flows[].steps[] 的每一步都必须携带 role、message、file_path、line_start、line_end、importance；AuditOutput.findings[] 不要输出函数级 code_map、taint_flow 或 steps[].function_name。
10. 如果 is_vulnerable 为 false，findings 必须为空数组，并且不要输出任何 data_flows。

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
