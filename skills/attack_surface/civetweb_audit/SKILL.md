---
name: civetweb_audit
description: Use when auditing CivetWeb HTTP/WebSocket attack surfaces, including
  handler discovery, external input tracing, vulnerability audit, and safe PoC validation.
required_audit_types:
- command_injection
- path_traversal
- brute_force
- password_reset
- loop
---

# CivetWeb Audit Skill

本 skill 覆盖 CivetWeb 攻击面的完整审计流程：入口发现、外部输入识别、数据流分析和 PoC 生成。

## 攻击面发现知识

发现所有 CivetWeb HTTP/WebSocket 入口函数。优先使用本 skill 子文件 `scripts/scan.py` 中的扫描策略；如果 runtime 无法直接运行脚本，则按下面的注册逻辑手动搜索源码。

### C API 注册

搜索路由注册调用：

- `mg_set_request_handler(ctx, "/path", callback, ...)`
- 项目封装的 CGI/路由注册，例如 `reg_cgi("/api/path", callback)`

识别规则：

1. 字符串参数通常是 route。
2. 函数指针参数通常是 callback。
3. callback 的真实函数定义是 `FunctionInfo` 入口。
4. 找不到真实函数定义、行号或代码片段的候选不要输出。

### C++ Handler

搜索：

- 继承 `CivetHandler` 或 `CivetRequestHandler` 的类。
- `handleGet`、`handlePost`、`handlePut`、`handleDelete`、`handlePatch`、`handleHead`、`handleOptions`。

这些 handler 方法接收 `mg_connection *conn`，应作为 Web 请求入口。

### WebSocket Handler

搜索：

- 继承 `CivetWebSocketHandler` 的类。
- `handleMessage` 方法。

`handleMessage` 的 `data` 和 `len` 是客户端可控输入。

### FunctionInfo 输出要求

每个入口必须输出：

- `func_name`
- `file_path`
- `start_line`
- `end_line`
- `code_snippet`
- `skill: "civetweb_audit"`

不要输出 Markdown，不要输出解释文字，只返回包含 `functions` 字段的 JSON object。

## 外部输入知识

### CivetWeb 外部输入点说明

CivetWeb HTTP/WebSocket 请求中的以下数据都应视为外部输入：

- `mg_get_var`
- `mg_get_header`
- `mg_get_cookie`
- `mg_get_form_var`
- `mg_read`
- `mg_get_request_info(conn)->request_uri`
- `mg_get_request_info(conn)->request_method`
- `mg_get_request_info(conn)->query_string`
- `mg_upload`
- `mg_handle_form_request` 回调参数
- `CivetHandler::handleGet/handlePost/...` 中的 `mg_connection *conn`
- `CivetWebSocketHandler::handleMessage` 中的 `data` 和 `len`

常见污染路径：

- 参数 -> 字符串拼接 -> `system` / `popen` / `exec*`
- 参数 -> 路径拼接 -> `fopen` / `open` / `unlink`
- 请求体或 JSON 字段 -> 长度、循环条件、索引、偏移
- 登录参数 -> 密码校验 -> 缺少失败次数、验证码或频率限制
- 重置密码参数 -> 新密码设置 -> 缺少旧密码、token 或验证码校验

Trace 要求：

1. 从当前 `FunctionInfo` 入口函数开始，不要全局扫描危险函数后直接下结论。
2. 优先识别入口函数中与 `conn`、`request_info`、`data`、`len`、请求体 buffer 相关的变量。
3. 沿参数传递、结构体字段、成员变量、全局对象、回调关系追踪数据流。
4. 只有外部输入能从入口函数传播到敏感操作时，才构成有效审计路径。
5. 不要把本 skill 文档当成 taint source；真正的 taint source 必须来自当前代码里的变量、参数或 API 调用。

## PoC 生成知识

PoC 必须安全、最小化、可复现，并且只验证当前 finding 描述的入口和数据流。

### HTTP PoC

如果 `FunctionInfo` 对应 route 可推断，优先生成 `curl` 请求：

```bash
curl -i 'http://TARGET/api/path?param=value'
```

对于命令注入，使用无害命令或可观察 echo 标记：

```bash
curl -i 'http://TARGET/api/path?name=%27%3B%20echo%20TSJ_AUDIT_SAFE%20%23'
```

对于路径遍历，只读取最小安全目标，不修改服务器状态：

```bash
curl -i 'http://TARGET/api/path?file=../../etc/passwd'
```

### POST / JSON PoC

如果入口读取 body 或 JSON 字段：

```bash
curl -i -X POST 'http://TARGET/api/path' \
  -H 'Content-Type: application/json' \
  --data '{"name":"test"}'
```

### WebSocket PoC

如果入口来自 `CivetWebSocketHandler::handleMessage`，生成可复现的 WebSocket 客户端脚本或命令，并说明目标 URI 和 payload。

### 约束

- 不要执行破坏性写入、删除、持久化后门或高负载请求。
- 如果没有可访问 URL，生成本地 harness 或可复现命令，并说明未执行原因。
- PoC 成功标准必须来自响应内容、状态码、服务日志、无害 echo 标记或可观察错误差异。
