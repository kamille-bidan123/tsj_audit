/**
 * CivetWeb 测试项目 - 包含安全漏洞的示例代码
 *
 * 编译方法:
 *   mkdir build && cd build
 *   cmake ..
 *   cmake --build .
 *
 * 运行：./build/server
 * 访问：http://localhost:8080/search?q=test
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "civetweb.h"

// 获取请求数据的辅助函数
static const char *get_var(struct mg_connection *conn, const char *name, char *buf, size_t buf_size)
{
    struct mg_request_info *ri = mg_get_request_info(conn);
    const char *query_string = ri->query_string;

    if (query_string == NULL) {
        return NULL;
    }

    // 使用 mg_get_var 从查询字符串中提取变量
    int len = mg_get_var(query_string, strlen(query_string), name, buf, buf_size);
    if (len > 0) {
        return buf;
    }
    return NULL;
}

// 危险处理函数 1: SQL 注入漏洞
static int handle_search(struct mg_connection *conn, void *cbdata)
{
    char query[256];
    char sql[512];
    char query_buf[1024];

    // 获取用户输入
    if (get_var(conn, "q", query_buf, sizeof(query_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameter 'q'");
        return 400;
    }

    strncpy(query, query_buf, sizeof(query) - 1);
    query[sizeof(query) - 1] = '\0';

    // 危险：直接拼接用户输入到 SQL 语句
    sprintf(sql, "SELECT * FROM products WHERE name LIKE '%%%s%%'", query);

    // 模拟执行 SQL
    printf("Executing SQL: %s\n", sql);

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n");
    mg_printf(conn, "<h1>Search Results</h1>");
    mg_printf(conn, "<p>Query: %s</p>", query);
    mg_printf(conn, "<p>SQL: %s</p>", sql);

    (void)cbdata;
    return 200;
}

// 危险处理函数 2: 命令注入漏洞
static int handle_system(struct mg_connection *conn, void *cbdata)
{
    char cmd[512];
    char action_buf[1024];

    if (get_var(conn, "action", action_buf, sizeof(action_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameter 'action'");
        return 400;
    }

    // 危险：命令注入
    sprintf(cmd, "echo 'Executing: %s' && date", action_buf);
    system(cmd);

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n");
    mg_printf(conn, "<h1>System Command</h1>");
    mg_printf(conn, "<p>Action: %s</p>", action_buf);

    (void)cbdata;
    return 200;
}

// 危险处理函数 3: 路径遍历漏洞
static int handle_file(struct mg_connection *conn, void *cbdata)
{
    char filepath[256];
    char buffer[1024];
    char filename_buf[1024];

    if (get_var(conn, "file", filename_buf, sizeof(filename_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameter 'file'");
        return 400;
    }

    // 危险：路径遍历
    sprintf(filepath, "/var/www/html/%s", filename_buf);

    FILE *f = fopen(filepath, "r");
    if (f == NULL) {
        mg_printf(conn, "HTTP/1.0 404 Not Found\r\n\r\nFile not found: %s", filepath);
        return 404;
    }

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n");
    while (fgets(buffer, sizeof(buffer), f)) {
        mg_write(conn, buffer, strlen(buffer));
    }
    fclose(f);

    (void)cbdata;
    return 200;
}

// 危险处理函数: 路径遍历漏洞 - 读取当前目录文件
static int handle_read(struct mg_connection *conn, void *cbdata)
{
    char filepath[512];
    char buffer[1024];
    char filename_buf[256];

    if (get_var(conn, "name", filename_buf, sizeof(filename_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameter 'name'");
        return 400;
    }

    // 危险：直接拼接用户输入，没有校验路径穿越
    // 攻击者可以使用 ../../../etc/passwd 读取任意文件
    sprintf(filepath, "./%s", filename_buf);

    FILE *f = fopen(filepath, "r");
    if (f == NULL) {
        mg_printf(conn, "HTTP/1.0 404 Not Found\r\n\r\nFile not found");
        return 404;
    }

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n");
    while (fgets(buffer, sizeof(buffer), f)) {
        mg_write(conn, buffer, strlen(buffer));
    }
    fclose(f);

    (void)cbdata;
    return 200;
}

// 危险处理函数 4: 缓冲区溢出 + 格式化字符串
static int handle_user(struct mg_connection *conn, void *cbdata)
{
    char name[64];
    char email[128];
    char response[512];
    char name_buf[1024];
    char email_buf[1024];

    if (get_var(conn, "name", name_buf, sizeof(name_buf)) == NULL ||
        get_var(conn, "email", email_buf, sizeof(email_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameters");
        return 400;
    }

    // 危险：没有检查长度
    strcpy(name, name_buf);
    strcpy(email, email_buf);

    // 危险：格式化字符串漏洞
    sprintf(response, name_buf);

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n");
    mg_printf(conn, "<h1>User Info</h1>");
    mg_printf(conn, "<p>Name: %s</p>", name);
    mg_printf(conn, "<p>Email: %s</p>", email);

    (void)cbdata;
    return 200;
}

// 安全处理函数示例 (正确的做法)
static int handle_safe(struct mg_connection *conn, void *cbdata)
{
    char input_buf[1024];

    if (get_var(conn, "data", input_buf, sizeof(input_buf)) == NULL) {
        mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nMissing parameter 'data'");
        return 400;
    }

    // 安全：使用 snprintf 限制长度
    char safe_buffer[256];
    snprintf(safe_buffer, sizeof(safe_buffer), "%s", input_buf);

    // 安全：对白名单字符进行验证
    for (char *p = safe_buffer; *p; p++) {
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9'))) {
            mg_printf(conn, "HTTP/1.0 400 Bad Request\r\n\r\nInvalid characters");
            return 400;
        }
    }

    mg_printf(conn, "HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n");
    mg_printf(conn, "<h1>Safe Handler</h1>");
    mg_printf(conn, "<p>Data: %s</p>", safe_buffer);

    (void)cbdata;
    return 200;
}

// 主程序
int main(void)
{
    struct mg_context *ctx;
    const char *options[] = {
        "listening_ports", "8080",
        "document_root", "./www",
        NULL
    };

    printf("CivetWeb Test Server\n");
    printf("====================\n\n");

    // 初始化 CivetWeb (禁用 TLS 避免 macOS 库加载问题)
    if (mg_init_library(0) != 0) {
        fprintf(stderr, "Failed to initialize CivetWeb library\n");
        return 1;
    }

    ctx = mg_start(NULL, NULL, options);
    if (ctx == NULL) {
        fprintf(stderr, "Cannot start server\n");
        mg_exit_library();
        return 1;
    }

    // 注册 URL 路由
    mg_set_request_handler(ctx, "/search", handle_search, NULL);
    mg_set_request_handler(ctx, "/system", handle_system, NULL);
    mg_set_request_handler(ctx, "/file", handle_file, NULL);
    mg_set_request_handler(ctx, "/read", handle_read, NULL);
    mg_set_request_handler(ctx, "/user", handle_user, NULL);
    mg_set_request_handler(ctx, "/safe", handle_safe, NULL);

    printf("Server started on port 8080\n");
    printf("\nTest endpoints:\n");
    printf("  - http://localhost:8080/search?q=test (SQL 注入)\n");
    printf("  - http://localhost:8080/system?action=ls (命令注入)\n");
    printf("  - http://localhost:8080/file?name=../../etc/passwd (路径遍历)\n");
    printf("  - http://localhost:8080/read?name=../../../etc/passwd (路径遍历 - 当前目录)\n");
    printf("  - http://localhost:8080/user?name=xxx&email=yyy (缓冲区溢出)\n");
    printf("  - http://localhost:8080/safe?data=hello (安全示例)\n");
    printf("\n按 Enter 键停止服务器...\n");

    // 等待退出信号
    getchar();

    mg_stop(ctx);
    mg_exit_library();

    printf("Server stopped.\n");
    return 0;
}
