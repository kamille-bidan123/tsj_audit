# Trace 阶段工具使用通用约束提示词


def get_trace_tool_guide() -> str:
    return """
## 工具使用原则

在代码污点追踪分析中，正确的工具使用顺序至关重要：

### 1. 优先使用 go_to_def 和 find_refs
- go_to_def: 跳转到函数/变量的定义处，查看下一级被调用的函数代码
- find_refs: 查找符号的所有引用，查看上一级调用它的函数

这两种工具能精确追踪数据流，是数据流分析的核心工具。

### 2. 谨慎使用 search_code
禁止使用 search_code 搜索通用关键词（如 "system", "exec", "fopen" 等危险函数）。

原因：
- 全局搜索会产生大量无关结果
- 关键词只有出现在接口函数能够碰到的数据流路径上才有意义
- 搜索危险函数本身没有意义，关键是分析外部输入是否会传递到这些函数

### 3. search_code 的正确使用场景
只有在以下特殊情况才使用 search_code：
- 遇到 RPC 调用时，搜索 RPC ID 来跟踪请求路由
- 遇到消息订阅/分发机制时，搜索 topic/channel ID 来跟踪消息流
- 遇到动态函数调用（函数指针、函数名拼接）时，搜索相关标识符

### 4. 工具使用优先级
优先级从高到低：
1. go_to_def - 追踪数据流向下一级函数
2. find_refs - 查找上一级调用者
3. read_file - 查看具体代码实现
4. list_dir - 查看目录结构（辅助）
5. search_code - 仅用于跟踪 RPCID/TopicID 等特殊情况

### 5. 正确的分析流程
1. 从接口函数开始
2. 使用 go_to_def 查看函数内部调用了哪些函数
3. 对每个被调用函数继续使用 go_to_def
4. 使用 find_refs 查找谁调用了当前函数，追溯数据来源
5. 重复步骤 2-4，直到追踪完整个数据流

## 错误示例

### 错误1：随意搜索危险函数
用户: 搜索代码中所有使用 system 函数的地方
AI: [使用 search_code 搜索 "system"]
结果: 找到几百个 system 调用，但不知道哪些与接口函数相关

### 错误2：没有追踪数据流直接看结果
用户: 这个函数有没有漏洞
AI: [直接搜索危险函数]
结果: 无法确定外部输入是否会传递到危险函数

### 错误3：跳过中间函数直接看终点
用户: 检查是否有命令注入
AI: [搜索 execve]
结果: 找到调用，但没有分析外部输入如何传递到这里

## 正确示例

### 正确1：从接口函数逐层追踪
1. [go_to_def] handle_login
   - 发现调用了: verify_password(user, password), create_session(user)

2. [go_to_def] verify_password
   - 发现调用了: query_db(sql), check_rate_limit(user)

3. [find_refs] query_db
   - 发现 sql 是由 "SELECT * FROM users WHERE user='" + user + "'" 构造
   - 外部输入 user 直接拼接到 SQL 中

4. [go_to_def] check_rate_limit
   - 发现没有实现任何限流逻辑

结论:
- 存在 SQL 注入漏洞（user 直接拼接到 SQL）
- 存在暴力破解漏洞（无限流）

### 正确2：使用 find_refs 追溯来源
1. [go_to_def] validate_input
   - 返回 sanitized_input

2. [find_refs] sanitized_input
   - 找到调用位置，发现来自原始输入但未做有效过滤

3. [go_to_def] 直接查看原始输入如何传递

### 正确3：特殊情况使用 search_code（RPC/消息分发场景）
场景1：函数指针/注册表方式
1. [go_to_def] handle_request
   - 发现调用了: dispatch(request->cmd_id, request->data)

2. [go_to_def] dispatch
   - 内部通过函数指针数组或 map 调用具体处理函数
   - 无法通过静态分析确定具体处理函数

3. [search_code] 搜索 cmd_id 或请求ID
   - 搜索 "cmd_id == 1" 或 "case CMD_LOGIN" 或 "handler_map["login"]"
   - 找到对应的处理函数指针或注册

4. [go_to_def] 根据找到的函数名跳转到实际处理函数
   - 继续正常的数据流分析

场景2：RPC 调用场景
1. [go_to_def] process_rpc
   - 发现调用了: rpc_call(RPC_LOGIN, user, password)

2. [go_to_def] rpc_call
   - 内部发送到消息队列或网络，不确定谁会接收

3. [search_code] 搜索 RPC_LOGIN
   - 搜索 "RPC_LOGIN" 或 "case RPC_LOGIN:" 或 "handler_RPC_LOGIN"
   - 找到接收并处理该 RPC 的函数

4. [go_to_def] 跳转到找到的处理函数
   - 继续追踪 user 和 password 的数据流向

## 总结

核心原则:
1. 数据流追踪: 从外部输入开始，沿着函数调用链追踪数据流向
2. 工具优先级: go_to_def/find_refs > read_file > search_code
3. 禁止全局搜索: search_code 仅用于跟踪 RPCID/TopicID 等特殊情况
4. 分析而非搜索: 关注数据流路径，而非寻找特定函数

请在分析过程中严格遵循以上原则。
"""


# 为了兼容旧代码，也提供一个常量
TRACE_TOOL_GUIDE = get_trace_tool_guide()