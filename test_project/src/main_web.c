/**
 * Web 服务进程 - HTTP请求处理
 * 处理所有HTTP请求，调用Worker进程处理业务逻辑
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include "civetweb.h"
#include "db.h"
#include "note_logic.h"

#define MAX_POST_DATA 65536
#define MAX_REPLY_LEN 65536

// 获取请求参数 - 适配 CivetWeb 1.16+ API
static const char* get_param(struct mg_connection* conn, const char* name, char* buf, size_t buf_size) {
    const struct mg_request_info* ri = mg_get_request_info(conn);

    // 先尝试从 query_string 获取 (GET 请求)
    if (ri->query_string) {
        int len = mg_get_var(ri->query_string, strlen(ri->query_string), name, buf, buf_size);
        if (len > 0) return buf;
    }

    // 尝试从 POST 数据获取
    // 读取 POST 数据
    char post_data[MAX_POST_DATA];
    int post_len = mg_read(conn, post_data, sizeof(post_data) - 1);
    if (post_len > 0) {
        post_data[post_len] = '\0';
        int len = mg_get_var(post_data, post_len, name, buf, buf_size);
        if (len > 0) return buf;
    }

    return NULL;
}

// 返回JSON响应
static void send_json(struct mg_connection* conn, int status, const char* message, const char* data) {
    char reply[MAX_REPLY_LEN];
    if (data) {
        snprintf(reply, sizeof(reply),
            "{\"status\":%d,\"message\":\"%s\",\"data\":%s}",
            status, message, data);
    } else {
        snprintf(reply, sizeof(reply),
            "{\"status\":%d,\"message\":\"%s\"}",
            status, message);
    }

    mg_printf(conn, "HTTP/1.1 %d OK\r\n", status);
    mg_printf(conn, "Content-Type: application/json\r\n");
    mg_printf(conn, "Access-Control-Allow-Origin: *\r\n");
    mg_printf(conn, "Content-Length: %zu\r\n", strlen(reply));
    mg_printf(conn, "\r\n");
    mg_write(conn, reply, strlen(reply));
}

// ==================== 处理函数 ====================

// 首页 - 返回静态 index.html 文件
static int handle_index(struct mg_connection* conn, void* cbdata) {
    FILE* f = fopen("./www/index.html", "r");
    if (f) {
        // 获取文件大小
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);

        // 读取文件内容
        char* html = (char*)malloc(size + 1);
        if (html) {
            fread(html, 1, size, f);
            html[size] = '\0';
            fclose(f);

            mg_printf(conn, "HTTP/1.1 200 OK\r\n");
            mg_printf(conn, "Content-Type: text/html; charset=utf-8\r\n");
            mg_printf(conn, "Content-Length: %lu\r\n", size);
            mg_printf(conn, "\r\n");
            mg_write(conn, html, size);
            free(html);
        }
        return 200;
    }

    // 如果文件不存在，返回简单的登录页面
    const char* html =
        "<!DOCTYPE html><html><head>"
        "<meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>记事本</title>"
        "<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>"
        "<script src='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'></script>"
        "</head><body><div class='container mt-5'>"
        "<h1 class='text-center mb-4'>记事本应用</h1>"
        "<div class='row justify-content-center'>"
        "<div class='col-md-6'>"
        "<div class='card'><div class='card-body'>"
        "<h5 class='card-title'>登录</h5>"
        "<form id='loginForm'>"
        "<div class='mb-3'><label class='form-label'>用户名</label><input type='text' class='form-control' id='username'></div>"
        "<div class='mb-3'><label class='form-label'>密码</label><input type='password' class='form-control' id='password'></div>"
        "<button type='submit' class='btn btn-primary'>登录</button>"
        "</form>"
        "<hr>"
        "<p class='text-center'><a href='#' onclick='showRegister()'>注册</a> | <a href='#' onclick='showForgotPassword()'>忘记密码</a></p>"
        "</div></div></div></div></div>"
        "<script>"
        "const API_URL = 'http://localhost:8081';"
        "document.getElementById('loginForm').onsubmit = async function(e){"
        "  e.preventDefault();"
        "  const username = document.getElementById('username').value;"
        "  const password = document.getElementById('password').value;"
        "  try {"
        "    const res = await fetch(API_URL + '/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });"
        "    const data = await res.json();"
        "    if (data.status === 200) { alert('登录成功！'); location.reload(); }"
        "    else alert('登录失败：' + data.message);"
        "  } catch (err) { alert('请求失败：' + err.message); }"
        "};"
        "function showRegister() { alert('请使用完整版 index.html'); }"
        "function showForgotPassword() { alert('请使用完整版 index.html'); }"
        "</script></body></html>";

    mg_printf(conn, "HTTP/1.1 200 OK\r\n");
    mg_printf(conn, "Content-Type: text/html; charset=utf-8\r\n");
    mg_printf(conn, "Content-Length: %zu\r\n", strlen(html));
    mg_printf(conn, "\r\n");
    mg_write(conn, html, strlen(html));
    return 200;
}

// 登录接口
static int handle_login(struct mg_connection* conn, void* cbdata) {
    char username[128], password[65];
    if (!get_param(conn, "username", username, sizeof(username)) ||
        !get_param(conn, "password", password, sizeof(password))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    LoginStatus status;
    int rc = note_login(username, password, &status);

    if (rc == 0) {
        char data[256];
        snprintf(data, sizeof(data), "{\"user_id\":%d,\"username\":\"%s\"}", status.user_id, status.username);
        send_json(conn, 200, "Login successful", data);
    } else if (rc == -1) {
        send_json(conn, 401, "Invalid password", NULL);
    } else if (rc == -2) {
        send_json(conn, 403, "Account locked", NULL);
    } else if (rc == -3) {
        send_json(conn, 403, "Account locked due to too many failed attempts", NULL);
    } else {
        send_json(conn, 404, "User not found", NULL);
    }
    return 200;
}

// 注册接口
static int handle_register(struct mg_connection* conn, void* cbdata) {
    char username[128], password[65], email[128];
    if (!get_param(conn, "username", username, sizeof(username)) ||
        !get_param(conn, "password", password, sizeof(password)) ||
        !get_param(conn, "email", email, sizeof(email))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    LoginStatus status;
    int rc = note_register(username, password, email, &status);

    if (rc == 0) {
        char data[256];
        snprintf(data, sizeof(data), "{\"user_id\":%d,\"username\":\"%s\"}", status.user_id, status.username);
        send_json(conn, 201, "Registration successful", data);
    } else if (rc == -1) {
        send_json(conn, 409, "User already exists", NULL);
    } else {
        send_json(conn, 500, "Registration failed", NULL);
    }
    return 200;
}

// 漏洞接口1：忘记密码 - 验证旧密码
static int handle_check_old_password(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32], old_password[65];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str)) ||
        !get_param(conn, "old_password", old_password, sizeof(old_password))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    send_json(conn, 200, "Old password verified", NULL);
    return 200;
}

// 漏洞接口2：忘记密码 - 重置密码
static int handle_reset_password(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32], new_password[65];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str)) ||
        !get_param(conn, "new_password", new_password, sizeof(new_password))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    int rc = note_reset_password(user_id, new_password);
    send_json(conn, rc == 0 ? 200 : 500, rc == 0 ? "Password reset successful" : "Password reset failed", NULL);
    return 200;
}

// 获取笔记列表
static int handle_get_notes(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str))) {
        send_json(conn, 400, "Missing user_id", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    Note notes[100];
    int count = 0;
    db_note_get_by_user(user_id, notes, &count, 100);

    char data[32768];
    char* p = data;
    char* end = p + sizeof(data) - 1;
    *p++ = '[';
    for (int i = 0; i < count && p < end; i++) {
        if (i > 0) *p++ = ',';
        p += snprintf(p, end - p,
            "{\"id\":%d,\"title\":\"%s\",\"content\":\"%s\",\"created_at\":\"%s\"}",
            notes[i].id, notes[i].title, notes[i].content, notes[i].created_at);
    }
    *p++ = ']';
    *p = '\0';

    send_json(conn, 200, "OK", data);
    return 200;
}

// 创建笔记
static int handle_create_note(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32], title[256];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str)) ||
        !get_param(conn, "title", title, sizeof(title))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    int note_id = 0;
    int rc = note_create_note(user_id, title, "", &note_id);

    if (rc == 0) {
        char data[64];
        snprintf(data, sizeof(data), "{\"note_id\":%d}", note_id);
        send_json(conn, 201, "Note created", data);
    } else {
        send_json(conn, 500, "Failed to create note", NULL);
    }
    return 200;
}

// 更新笔记
static int handle_update_note(struct mg_connection* conn, void* cbdata) {
    char note_id_str[32], title[256];
    if (!get_param(conn, "note_id", note_id_str, sizeof(note_id_str)) ||
        !get_param(conn, "title", title, sizeof(title))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    int note_id = atoi(note_id_str);
    int rc = note_update_note(note_id, title, "");
    send_json(conn, rc == 0 ? 200 : 404, rc == 0 ? "Note updated" : "Note not found", NULL);
    return 200;
}

// 删除笔记
static int handle_delete_note(struct mg_connection* conn, void* cbdata) {
    char note_id_str[32];
    if (!get_param(conn, "note_id", note_id_str, sizeof(note_id_str))) {
        send_json(conn, 400, "Missing note_id", NULL);
        return 200;
    }

    int note_id = atoi(note_id_str);
    int rc = note_delete_note(note_id);
    send_json(conn, rc == 0 ? 200 : 404, rc == 0 ? "Note deleted" : "Note not found", NULL);
    return 200;
}

// 永久删除笔记
static int handle_force_delete_note(struct mg_connection* conn, void* cbdata) {
    char note_id_str[32];
    if (!get_param(conn, "note_id", note_id_str, sizeof(note_id_str))) {
        send_json(conn, 400, "Missing note_id", NULL);
        return 200;
    }

    int note_id = atoi(note_id_str);
    int rc = note_force_delete_note(note_id);
    send_json(conn, rc == 0 ? 200 : 404, rc == 0 ? "Note permanently deleted" : "Note not found", NULL);
    return 200;
}

// 获取FTP配置
static int handle_get_ftp_config(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str))) {
        send_json(conn, 400, "Missing user_id", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    FtpConfig config;
    int rc = db_ftp_config_get_by_user(user_id, &config);

    if (rc == 0) {
        char data[512];
        snprintf(data, sizeof(data), "{\"host\":\"%s\",\"port\":%d,\"user\":\"%s\",\"path\":\"%s\"}",
            config.ftp_host, config.ftp_port, config.ftp_user, config.ftp_path);
        send_json(conn, 200, "OK", data);
    } else {
        send_json(conn, 404, "FTP config not found", NULL);
    }
    return 200;
}

// 保存FTP配置
static int handle_save_ftp_config(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32], host[256], port_str[16], user[128];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str)) ||
        !get_param(conn, "host", host, sizeof(host)) ||
        !get_param(conn, "port", port_str, sizeof(port_str)) ||
        !get_param(conn, "user", user, sizeof(user))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    int port = atoi(port_str);
    int rc = db_ftp_config_update(user_id, host, port, user, "", "/");

    send_json(conn, rc == 0 ? 200 : 500, rc == 0 ? "FTP config saved" : "Failed to save FTP config", NULL);
    return 200;
}

// 漏洞接口：上传笔记到FTP（存在命令注入）
static int handle_upload_notes(struct mg_connection* conn, void* cbdata) {
    char user_id_str[32], host[256];
    if (!get_param(conn, "user_id", user_id_str, sizeof(user_id_str)) ||
        !get_param(conn, "host", host, sizeof(host))) {
        send_json(conn, 400, "Missing parameters", NULL);
        return 200;
    }

    int user_id = atoi(user_id_str);
    int rc = note_upload_notes_to_ftp(user_id, host, "/");

    send_json(conn, rc == 0 ? 200 : 500, rc == 0 ? "Notes uploaded to FTP" : "Failed to upload notes", NULL);
    return 200;
}

// 漏洞接口：上传logo（路径穿越）
static int handle_upload_logo(struct mg_connection* conn, void* cbdata) {
    char filename[256];
    if (!get_param(conn, "filename", filename, sizeof(filename))) {
        send_json(conn, 400, "Missing filename", NULL);
        return 200;
    }

    // 漏洞：直接拼接路径
    char filepath[512];
    snprintf(filepath, sizeof(filepath), "./www/upload/%s", filename);

    mkdir("./www/upload", 0755);
    FILE* f = fopen(filepath, "w");
    if (f) {
        fprintf(f, "Logo uploaded: %s\n", filename);
        fclose(f);
        send_json(conn, 200, "Logo uploaded", NULL);
    } else {
        send_json(conn, 500, "Failed to upload", NULL);
    }
    return 200;
}

// 路由表
static struct {
    const char* path;
    int (*handler)(struct mg_connection* conn, void* cbdata);
} g_routes[] = {
    {"/", handle_index},
    {"/login", handle_login},
    {"/register", handle_register},
    {"/check_old_password", handle_check_old_password},
    {"/reset_password", handle_reset_password},
    {"/notes", handle_get_notes},
    {"/notes", handle_create_note},
    {"/notes", handle_update_note},
    {"/notes/delete", handle_delete_note},
    {"/notes/force_delete", handle_force_delete_note},
    {"/ftp/config", handle_get_ftp_config},
    {"/ftp/save", handle_save_ftp_config},
    {"/ftp/upload", handle_upload_notes},
    {"/logo/upload", handle_upload_logo},
    {NULL, NULL}
};

int main(int argc, char* argv[]) {
    printf("Web Server Starting...\n");
    printf("=====================\n\n");

    if (note_logic_init() != 0) {
        fprintf(stderr, "Failed to initialize note logic\n");
        return 1;
    }

    struct mg_context* ctx;
    const char* options[] = {
        "listening_ports", "8081",
        "document_root", "./www",
        NULL
    };

    if (mg_init_library(0) != 0) {
        fprintf(stderr, "Failed to initialize CivetWeb\n");
        return 1;
    }

    ctx = mg_start(NULL, NULL, options);
    if (ctx == NULL) {
        fprintf(stderr, "Failed to start server\n");
        mg_exit_library();
        return 1;
    }

    // 注册路由
    for (int i = 0; g_routes[i].path != NULL; i++) {
        mg_set_request_handler(ctx, g_routes[i].path, g_routes[i].handler, NULL);
    }

    printf("Web server started on port 8081\n");
    printf("\nAvailable endpoints:\n");
    for (int i = 0; g_routes[i].path != NULL; i++) {
        printf("  - %s\n", g_routes[i].path);
    }

    printf("\n按 Enter 键停止服务器...\n");
    getchar();

    mg_stop(ctx);
    mg_exit_library();
    db_close();

    printf("Server stopped.\n");
    return 0;
}
