# CivetWeb 外部输入点说明

## 概述

CivetWeb 是一个用 C 语言编写的嵌入式 Web 服务器。本文件描述了从外部请求到内部函数调用的数据流污染路径。

## 外部输入来源

### 1. HTTP 请求参数

通过 `mg_get_var`、`mg_get_header` 等函数获取的用户输入：

```c
// 查询参数
const char *query = mg_get_var(conn, "param_name");

// HTTP 头
const char *auth = mg_get_header(conn, "Authorization");

// POST 数据
char post_data[1024];
mg_read(conn, post_data, sizeof(post_data));
```

### 2. URL 路径参数

URL 路径本身可能包含用户控制的输入：

```c
// 请求的 URI
const char *uri = mg_get_request_info(conn)->request_uri;
const char *method = mg_get_request_info(conn)->request_method;
```

### 3. 文件上传

通过 `mg_upload` 或直接读取请求体：

```c
// 文件上传
mg_upload(conn, "/tmp");

// 原始请求体
mg_read(conn, buffer, len);
```

## 常见污染路径

### 路径 1: 参数 -> sprintf -> 缓冲区溢出
```c
char buffer[256];
const char *user_input = mg_get_var(conn, "name");
sprintf(buffer, "SELECT * FROM users WHERE name='%s'", user_input);  // SQL 注入
```

### 路径 2: 参数 -> system/exec -> 命令注入
```c
const char *cmd = mg_get_var(conn, "command");
char sys_cmd[512];
sprintf(sys_cmd, "ls -la %s", cmd);
system(sys_cmd);  // 命令注入
```

### 路径 3: 参数 -> 文件操作 -> 路径遍历
```c
const char *file = mg_get_var(conn, "filename");
char path[256];
sprintf(path, "/var/www/html/%s", file);
FILE *f = fopen(path, "r");  // 路径遍历
```

## 需要审计的函数模式

1. **直接用户输入使用**：`mg_get_var`, `mg_read`, `mg_get_header`
2. **字符串拼接**：`sprintf`, `strcat`, `strcpy`
3. **危险函数调用**：`system`, `exec*`, `popen`, `fopen`
4. **SQL 查询构造**：包含 SQL 关键字的字符串格式化

## 示例输入点

| 函数/位置 | 输入类型 | 风险等级 |
|-----------|----------|----------|
| mg_get_var(conn, "*") | GET/POST 参数 | 高 |
| mg_get_header(conn, "*") | HTTP 头 | 中 |
| mg_read(conn, buf, len) | 请求体 | 高 |
| mg_get_request_info(conn) | URI/Method | 中 |
