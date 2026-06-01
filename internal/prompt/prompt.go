package prompt

import (
	"encoding/json"
	"fmt"
	"strings"
)

type Options struct {
	Runtime     string
	StageName   string
	ProjectPath string
	System      string
	User        string
	Schema      json.RawMessage
}

func BuildUnified(options Options) string {
	projectPathGuidance := fmt.Sprintf(
		"- 待审计源码根目录：%s。\n"+
			"- EntrySpec.file_path 是相对待审计源码根目录的路径；读取源码时请解析为 源码根目录/file_path。\n"+
			"- 如果需要查看源码，请只读取待审计源码根目录内文件。\n",
		options.ProjectPath,
	)
	if strings.EqualFold(options.Runtime, "opencode") {
		projectPathGuidance = fmt.Sprintf(
			"- OpenCode 当前会话目录已经设置为待审计源码根目录：%s。\n"+
				"- EntrySpec.file_path 是相对当前会话目录的路径；读取源码时必须直接使用 EntrySpec.file_path。\n"+
				"- 不要给源码路径添加 project_path、../ 前缀或绝对路径前缀。\n"+
				"- 如果需要查看源码，请只读取当前会话目录内文件。\n",
			options.ProjectPath,
		)
	}
	return fmt.Sprintf(
		"## Unified System Prompt\n%s\n\n"+
			"## Runtime\n"+
			"- 当前由 %s 运行 %s 阶段。\n"+
			"%s"+
			"- 最终回答必须是满足下方 JSON Schema 的 JSON 对象，不要输出 Markdown。\n"+
			"- 所有 FunctionInfo、CodeMap、skill、runtime、schema 等字段注入都只存在于本统一 system prompt 中。\n\n"+
			"## JSON Schema\n%s\n\n"+
			"## User Task\n%s",
		options.System,
		options.Runtime,
		options.StageName,
		projectPathGuidance,
		string(options.Schema),
		options.User,
	)
}

func SkillUsage(skillName, relativeSkillFile string) string {
	if skillName == "" || relativeSkillFile == "" {
		return ""
	}
	return fmt.Sprintf(`## Attack Surface Skill
当前任务声明了攻击面 skill：%q。
该攻击面 skill 已安装或位于当前项目内：%q。

强制要求：
- 在 discovery/trace/audit/exploit 前必须使用该 skill 中的攻击面发现知识、外部输入知识、数据流分析知识和 PoC 生成知识。
- 如果当前 runtime 提供 skill 工具，请先加载该 skill。
- 如果当前 runtime 不提供 skill 工具，请直接读取该 skill 文件，并按其中的知识进行数据流追踪。
- 不要把 skill 文档本身当成具体污染源；具体 taint_source 必须来自当前函数代码中的变量、参数或 API 调用。`, skillName, relativeSkillFile)
}
