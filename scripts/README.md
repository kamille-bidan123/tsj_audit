# 审计结果导出工具

此脚本用于将审计检查点合并并导出为多种格式。

## 功能

- 将 `checkpoints` 目录中的所有审计检查点合并
- 导出为多种格式以供进一步分析：
  - **JSON**: 完整的审计结果数据
  - **HTML**: 交互式可视化报告
  - **Markdown**: 每个函数一个 Markdown 审计报告，分别输出全量目录和有漏洞目录
  - **SARIF**: 静态分析结果交换格式（标准格式）
  - **SARIF-ISSUES**: 仅包含问题的 SARIF 格式

## 用法

```bash
python scripts/export_results.py <output_dir>
```

### 参数

- `output_dir`: 输出目录路径，该目录应包含 `checkpoints` 子目录

### 选项

- `--debug`, `-d`: 启用调试模式，显示详细信息

## 示例

```bash
# 导出审计结果
python scripts/export_results.py ./audit_results

# 调试模式导出
python scripts/export_results.py ./audit_results --debug
```

## 输出文件

脚本会在指定的输出目录中生成以下文件：

- `trace_results_YYYYMMDD_HHMMSS.json` - JSON 格式的完整审计结果
- `trace_results_YYYYMMDD_HHMMSS.html` - HTML 格式的交互式报告
- `trace_results_YYYYMMDD_HHMMSS_markdown/` - Markdown 格式的函数报告目录，包含 `all/` 和 `vulnerable/`
- `trace_results_YYYYMMDD_HHMMSS.sarif` - SARIF 格式的完整分析结果
- `trace_results_YYYYMMDD_HHMMSS_issues.sarif` - SARIF 格式的仅问题报告

## 文件说明

- **JSON 格式**: 适用于程序化处理和进一步分析
- **HTML 格式**: 提供交互式界面，便于人工审查
- **Markdown 格式**: 生成全量函数和有漏洞函数两套索引与每函数报告，便于人工确认、摘录和发送
- **SARIF 格式**: 与其他静态分析工具兼容的标准格式
- **SARIF-ISSUES 格式**: 专注于识别的问题，便于集成到 CI/CD 流程
