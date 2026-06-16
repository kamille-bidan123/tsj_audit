# 审计结果导出工具

Go 版导出命令用于将审计检查点合并并导出为多种格式。

## 功能

- 将 `checkpoints` 目录中的所有审计检查点合并
- 导出为多种格式以供进一步分析：
  - **JSON**: 完整的审计结果数据
  - **HTML**: 审计报告
  - **Markdown**: 审计报告
  - **SARIF**: 静态分析结果交换格式（标准格式）
  - **SARIF-ISSUES**: 仅包含问题的 SARIF 格式

## 用法

```bash
go run ./cmd/export-results --output-dir <output_dir>
```

### 参数

- `output_dir`: 输出目录路径，该目录应包含 `checkpoints` 子目录
- `--inherit-sarif <old.sarif>`: 读取 `<old.sarif>.sarifexplorer` 中的 SARIF Explorer 人工审核 `status/comment`，并迁移到新导出的 `.sarifexplorer` 文件

## 示例

```bash
# 导出审计结果
go run ./cmd/export-results --output-dir ./audit_results

# 导出并继承旧 SARIF Explorer 审核结果
go run ./cmd/export-results --output-dir ./audit_results --inherit-sarif ./old_reviewed.sarif
```

## 输出文件

脚本会在指定的输出目录中生成以下文件：

- `audit_results.json` - JSON 格式的完整审计结果
- `audit_report.md` - Markdown 审计报告
- `audit_report.html` - HTML 审计报告
- `audit_report.sarif` - SARIF 格式的完整分析结果
- `audit_issues.sarif` - SARIF 格式的仅问题报告
- `audit_report.sarif.sarifexplorer` - 使用 `--inherit-sarif` 时生成的 SARIF Explorer 人工审核结果
- `audit_issues.sarif.sarifexplorer` - 使用 `--inherit-sarif` 时生成的仅问题 SARIF Explorer 人工审核结果

## 文件说明

- **JSON 格式**: 适用于程序化处理和进一步分析
- **HTML 格式**: 便于人工审查
- **Markdown 格式**: 便于人工确认、摘录和发送
- **SARIF 格式**: 与其他静态分析工具兼容的标准格式
- **SARIF-ISSUES 格式**: 专注于识别的问题，便于集成到 CI/CD 流程
