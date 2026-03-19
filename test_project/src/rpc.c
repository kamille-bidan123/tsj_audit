/**
 * RPC 实现
 */
#include "rpc.h"
#include "db.h"
#include "utils.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include <time.h>

rpc_handler_t g_handlers[RPC_LAST_OP] = {0};

static int handle_ping(const rpc_request_t* request, rpc_response_t* response) {
    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "pong");
    return 0;
}

static int handle_login(const rpc_request_t* request, rpc_response_t* response) {
    User user;
    int rc = db_user_get_by_username(request->username, &user);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "User not found");
        return -1;
    }

    // 检查是否被锁定
    if (db_user_is_locked(user.id)) {
        response->status = RPC_ERROR_FAILED;
        snprintf(response->message, sizeof(response->message), "Account is locked due to too many failed attempts");
        return -1;
    }

    // 检查密码
    if (strcmp(user.password_hash, request->password) != 0) {
        db_user_increment_login_fail(user.id);

        // 额外的漏洞：登录失败计数检查逻辑有缺陷
        // 检查是否达到3次失败
        if (db_user_check_login_fail_limit(user.id)) {
            db_user_lock(user.id);
            response->status = RPC_ERROR_FAILED;
            snprintf(response->message, sizeof(response->message), "Account locked due to too many failed attempts");
        } else {
            response->status = RPC_ERROR_FAILED;
            snprintf(response->message, sizeof(response->message), "Invalid password");
        }
        return -1;
    }

    // 登录成功，重置失败计数
    db_user_reset_login_fail(user.id);

    response->status = RPC_SUCCESS;
    response->user_id = user.id;
    snprintf(response->message, sizeof(response->message), "Login successful");
    return 0;
}

static int handle_register(const rpc_request_t* request, rpc_response_t* response) {
    // 检查用户是否已存在
    if (db_user_exists(request->username)) {
        response->status = RPC_ERROR_FAILED;
        snprintf(response->message, sizeof(response->message), "User already exists");
        return -1;
    }

    int rc = db_user_create(request->username, request->password, request->email);
    if (rc != 0) {
        response->status = RPC_ERROR_INTERNAL;
        snprintf(response->message, sizeof(response->message), "Failed to create user");
        return -1;
    }

    // 获取新用户ID
    User user;
    db_user_get_by_username(request->username, &user);

    response->status = RPC_SUCCESS;
    response->user_id = user.id;
    snprintf(response->message, sizeof(response->message), "Registration successful");
    return 0;
}

static int handle_get_notes(const rpc_request_t* request, rpc_response_t* response) {
    Note notes[100];
    int count = 0;

    int rc = db_note_get_by_user(request->user_id, notes, &count, 100);
    if (rc != 0) {
        response->status = RPC_ERROR_INTERNAL;
        snprintf(response->message, sizeof(response->message), "Failed to get notes");
        return -1;
    }

    // 构建JSON响应
    char* p = response->notes_data;
    char* end = p + sizeof(response->notes_data) - 1;

    *p++ = '[';

    for (int i = 0; i < count && p < end; i++) {
        if (i > 0) *p++ = ',';
        p += snprintf(p, end - p,
            "{\"id\":%d,\"title\":\"%s\",\"content\":\"%s\",\"created_at\":\"%s\",\"updated_at\":\"%s\"}",
            notes[i].id, notes[i].title, notes[i].content, notes[i].created_at, notes[i].updated_at);
    }

    *p++ = ']';
    *p = '\0';

    response->status = RPC_SUCCESS;
    response->note_count = count;
    snprintf(response->message, sizeof(response->message), "OK");
    return 0;
}

static int handle_get_note(const rpc_request_t* request, rpc_response_t* response) {
    Note note;
    int rc = db_note_get_by_id(request->note_id, &note);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "Note not found");
        return -1;
    }

    response->status = RPC_SUCCESS;
    response->note_id = note.id;
    strncpy(response->notes_data, note.content, sizeof(response->notes_data) - 1);
    snprintf(response->message, sizeof(response->message), "OK");
    return 0;
}

static int handle_create_note(const rpc_request_t* request, rpc_response_t* response) {
    // 漏洞：没有检查标题和内容长度，可能导致缓冲区溢出
    // 但这里我们做安全处理，不过在日志中会显示原始输入

    int rc = db_note_create(request->user_id, request->title, request->content);
    if (rc != 0) {
        response->status = RPC_ERROR_INTERNAL;
        snprintf(response->message, sizeof(response->message), "Failed to create note");
        return -1;
    }

    // 获取刚创建的笔记ID
    Note note;
    char sql[256];
    snprintf(sql, sizeof(sql), "SELECT last_insert_rowid()");
    sqlite3* db = db_get_connection();
    sqlite3_stmt* stmt;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            response->note_id = sqlite3_column_int(stmt, 0);
        }
        sqlite3_finalize(stmt);
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Note created");
    return 0;
}

static int handle_update_note(const rpc_request_t* request, rpc_response_t* response) {
    int rc = db_note_update(request->note_id, request->title, request->content);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "Failed to update note");
        return -1;
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Note updated");
    return 0;
}

static int handle_delete_note(const rpc_request_t* request, rpc_response_t* response) {
    int rc = db_note_delete(request->note_id);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "Failed to delete note");
        return -1;
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Note deleted");
    return 0;
}

static int handle_restore_note(const rpc_request_t* request, rpc_response_t* response) {
    int rc = db_note_restore(request->note_id);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "Failed to restore note");
        return -1;
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Note restored");
    return 0;
}

static int handle_force_delete_note(const rpc_request_t* request, rpc_response_t* response) {
    int rc = db_note_force_delete(request->note_id);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "Failed to permanently delete note");
        return -1;
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Note permanently deleted");
    return 0;
}

static int handle_get_ftp_config(const rpc_request_t* request, rpc_response_t* response) {
    FtpConfig config;
    int rc = db_ftp_config_get_by_user(request->user_id, &config);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "FTP config not found");
        return -1;
    }

    response->status = RPC_SUCCESS;
    response->ftp_port = config.ftp_port;
    strncpy(response->ftp_host, config.ftp_host, sizeof(response->ftp_host) - 1);
    strncpy(response->ftp_user, config.ftp_user, sizeof(response->ftp_user) - 1);
    strncpy(response->ftp_path, config.ftp_path, sizeof(response->ftp_path) - 1);
    snprintf(response->message, sizeof(response->message), "OK");
    return 0;
}

static int handle_update_ftp_config(const rpc_request_t* request, rpc_response_t* response) {
    int rc = db_ftp_config_update(request->user_id, request->ftp_host,
                                   request->ftp_port, request->ftp_user,
                                   request->ftp_pass, request->ftp_path);
    if (rc != 0) {
        response->status = RPC_ERROR_INTERNAL;
        snprintf(response->message, sizeof(response->message), "Failed to update FTP config");
        return -1;
    }

    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "FTP config saved");
    return 0;
}

// 漏洞函数：上传笔记到FTP，存在命令注入
static int handle_upload_notes_to_ftp(const rpc_request_t* request, rpc_response_t* response) {
    FtpConfig config;
    int rc = db_ftp_config_get_by_user(request->user_id, &config);
    if (rc != 0) {
        response->status = RPC_ERROR_NOT_FOUND;
        snprintf(response->message, sizeof(response->message), "FTP config not found");
        return -1;
    }

    // 漏洞点1：先保存配置
    rc = db_ftp_config_update(request->user_id, request->ftp_host,
                               request->ftp_port, request->ftp_user,
                               request->ftp_pass, request->ftp_path);
    if (rc != 0) {
        response->status = RPC_ERROR_INTERNAL;
        snprintf(response->message, sizeof(response->message), "Failed to save FTP config");
        return -1;
    }

    // 漏洞点2：上传前用system拼接IP做ping测试
    char cmd[512];

    // 漏洞：这里直接拼接用户输入的FTP主机名
    // 攻击者可以注入: 192.168.1.1; cat /etc/passwd
    snprintf(cmd, sizeof(cmd), "ping -c 1 %s > /dev/null 2>&1 && echo OK", config.ftp_host);

    // 命令注入漏洞点
    int ping_result = system(cmd);

    if (ping_result != 0) {
        response->status = RPC_ERROR_FAILED;
        snprintf(response->message, sizeof(response->message), "Cannot connect to FTP server");
        return -1;
    }

    // 模拟上传成功
    response->status = RPC_SUCCESS;
    snprintf(response->message, sizeof(response->message), "Notes uploaded to FTP");
    return 0;
}

int rpc_init(void) {
    // 创建命名管道
    if (mkfifo(RPC_PIPE_PATH, 0666) == -1) {
        if (errno != EEXIST) {
            fprintf(stderr, "Failed to create FIFO: %s\n", strerror(errno));
            return -1;
        }
    }

    // 注册默认处理器
    rpc_register_handler(RPC_PING, handle_ping);
    rpc_register_handler(RPC_LOGIN, handle_login);
    rpc_register_handler(RPC_REGISTER, handle_register);
    rpc_register_handler(RPC_GET_NOTES, handle_get_notes);
    rpc_register_handler(RPC_GET_NOTE, handle_get_note);
    rpc_register_handler(RPC_CREATE_NOTE, handle_create_note);
    rpc_register_handler(RPC_UPDATE_NOTE, handle_update_note);
    rpc_register_handler(RPC_DELETE_NOTE, handle_delete_note);
    rpc_register_handler(RPC_RESTORE_NOTE, handle_restore_note);
    rpc_register_handler(RPC_FORCE_DELETE_NOTE, handle_force_delete_note);
    rpc_register_handler(RPC_GET_FTP_CONFIG, handle_get_ftp_config);
    rpc_register_handler(RPC_UPDATE_FTP_CONFIG, handle_update_ftp_config);
    rpc_register_handler(RPC_UPLOAD_NOTES_TO_FTP, handle_upload_notes_to_ftp);

    fprintf(stderr, "[RPC] Initialized\n");
    return 0;
}

int rpc_register_handler(uint32_t op, rpc_handler_t handler) {
    if (op >= RPC_LAST_OP) {
        return -1;
    }
    g_handlers[op] = handler;
    return 0;
}

size_t rpc_get_request_size(const rpc_request_t* request) {
    return sizeof(rpc_request_t);
}

size_t rpc_get_response_size(const rpc_response_t* response) {
    return sizeof(rpc_response_t);
}

int rpc_send_request(const rpc_request_t* request, rpc_response_t* response) {
    // 尝试通过 FIFO 与 Worker 进程通信
    int fifo_fd = open(RPC_PIPE_PATH, O_RDWR);
    if (fifo_fd == -1) {
        // Worker 进程未启动，降级到本地调用
        if (request->op >= RPC_LAST_OP || g_handlers[request->op] == NULL) {
            response->request_id = request->request_id;
            response->status = RPC_ERROR_INTERNAL;
            snprintf(response->message, sizeof(response->message), "Unknown operation");
            return -1;
        }
        memset(response, 0, sizeof(*response));
        response->request_id = request->request_id;
        return g_handlers[request->op](request, response);
    }

    // 写入请求
    ssize_t written = write(fifo_fd, request, sizeof(*request));
    if (written == -1) {
        fprintf(stderr, "[RPC] Write to FIFO failed: %s\n", strerror(errno));
        close(fifo_fd);
        return -1;
    }

    // 读取响应
    ssize_t n = read(fifo_fd, response, sizeof(*response));
    close(fifo_fd);

    if (n == -1) {
        fprintf(stderr, "[RPC] Read from FIFO failed: %s\n", strerror(errno));
        return -1;
    }

    return 0;
}

void rpc_close(void) {
    // 清理资源
}
