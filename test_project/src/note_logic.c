/**
 * 笔记业务逻辑实现
 * 通过 RPC 调用 Worker 进程处理业务逻辑
 */
#include "note_logic.h"
#include "utils.h"
#include "rpc.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// 全局 RPC 请求 ID 计数器
static uint32_t g_request_id = 0;

// 发送 RPC 请求并等待响应
static int rpc_call(rpc_op_t op, const rpc_request_t* request, rpc_response_t* response) {
    // 初始化响应
    memset(response, 0, sizeof(*response));
    response->request_id = g_request_id++;

    // 设置操作码
    rpc_request_t req = *request;
    req.op = op;

    // 发送请求
    int rc = rpc_send_request(&req, response);
    return rc;
}

int note_logic_init(void) {
    // 初始化数据库（用于本地缓存等）
    db_init();
    return 0;
}

// 漏洞函数1：忘记密码功能
// 问题：前端有输入旧密码，但后端两个接口，一个确认旧密码，一个直接重置密码
int note_check_old_password(int user_id, const char* old_password) {
    // 使用 Worker 进程验证密码
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    strncpy(request.password, old_password, sizeof(request.password) - 1);

    // 直接调用本地 handle_login 处理器（因为 Worker 还没启动）
    // 实际生产环境应该通过 RPC 调用
    User user;
    if (db_user_get_by_id(user_id, &user) != 0) {
        return -1;
    }
    return strcmp(user.password_hash, old_password) == 0 ? 0 : -1;
}

int note_reset_password(int user_id, const char* new_password) {
    // 通过 RPC 调用 Worker 进程重置密码
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    strncpy(request.password, new_password, sizeof(request.password) - 1);
    request.op = RPC_LOGIN;  // 复用登录操作码，实际应添加新的操作码

    // 简化实现：由于 rpc_send_request 是简化版，直接调用本地处理器
    // 真正的跨进程调用需要启动 Worker 进程并通过 FIFO 通信
    return db_user_update_password(user_id, new_password);
}

// 登录处理
int note_login(const char* username, const char* password, LoginStatus* status) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    memset(status, 0, sizeof(*status));

    // 设置请求
    strncpy(request.username, username, sizeof(request.username) - 1);
    strncpy(request.password, password, sizeof(request.password) - 1);

    // 发送 RPC 请求
    int rc = rpc_call(RPC_LOGIN, &request, &response);
    if (rc != 0 || response.status != RPC_SUCCESS) {
        // 如果 RPC 失败，尝试本地处理（用于测试）
        User user;
        int db_rc = db_user_get_by_username(username, &user);
        if (db_rc != 0) {
            return -1;  // 用户不存在
        }

        // 检查是否被锁定
        if (db_user_is_locked(user.id)) {
            return -2;  // 账户被锁定
        }

        // 检查密码
        if (strcmp(user.password_hash, password) != 0) {
            db_user_increment_login_fail(user.id);
            if (db_user_check_login_fail_limit(user.id)) {
                db_user_lock(user.id);
                return -3;  // 超过限制被锁定
            }
            return -1;  // 密码错误
        }

        // 登录成功
        db_user_reset_login_fail(user.id);

        status->is_logged_in = 1;
        status->user_id = user.id;
        strncpy(status->username, user.username, sizeof(status->username) - 1);
        return 0;
    }

    // RPC 成功
    status->is_logged_in = 1;
    status->user_id = response.user_id;
    strncpy(status->username, username, sizeof(status->username) - 1);
    return 0;
}

// 注册处理
int note_register(const char* username, const char* password, const char* email, LoginStatus* status) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    memset(status, 0, sizeof(*status));

    // 设置请求
    strncpy(request.username, username, sizeof(request.username) - 1);
    strncpy(request.password, password, sizeof(request.password) - 1);
    strncpy(request.email, email, sizeof(request.email) - 1);

    // 发送 RPC 请求
    int rc = rpc_call(RPC_REGISTER, &request, &response);
    if (rc != 0 || response.status != RPC_SUCCESS) {
        // RPC 失败，使用本地处理
        if (db_user_exists(username)) {
            return -1;  // 用户已存在
        }

        int db_rc = db_user_create(username, password, email);
        if (db_rc != 0) {
            return -2;  // 创建失败
        }

        User user;
        if (db_user_get_by_username(username, &user) != 0) {
            return -3;  // 获取失败
        }

        status->is_logged_in = 1;
        status->user_id = user.id;
        strncpy(status->username, user.username, sizeof(status->username) - 1);
        return 0;
    }

    // RPC 成功
    status->is_logged_in = 1;
    status->user_id = response.user_id;
    strncpy(status->username, username, sizeof(status->username) - 1);
    return 0;
}

// 获取用户笔记列表
int note_get_user_notes(int user_id, Note* notes, int* count, int max_count) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    request.op = RPC_GET_NOTES;

    int rc = rpc_call(RPC_GET_NOTES, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        // 解析响应中的笔记数据
        *count = response.note_count;
        if (*count > 0 && notes && max_count > 0) {
            // 简化：由于 RPC 响应中 notes_data 是 JSON 格式，
            // 真正实现需要解析 JSON
            // 这里先使用本地数据库查询
            return db_note_get_by_user(user_id, notes, count, max_count);
        }
        return 0;
    }

    // RPC 失败，使用本地查询
    return db_note_get_by_user(user_id, notes, count, max_count);
}

// 获取单个笔记
int note_get_note(int note_id, Note* note) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.note_id = note_id;
    request.op = RPC_GET_NOTE;

    int rc = rpc_call(RPC_GET_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        // 简化实现
        return db_note_get_by_id(note_id, note);
    }
    return db_note_get_by_id(note_id, note);
}

// 创建笔记
int note_create_note(int user_id, const char* title, const char* content, int* note_id) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    strncpy(request.title, title, sizeof(request.title) - 1);
    strncpy(request.content, content, sizeof(request.content) - 1);
    request.op = RPC_CREATE_NOTE;

    int rc = rpc_call(RPC_CREATE_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        *note_id = response.note_id;
        return 0;
    }

    // RPC 失败，使用本地创建
    int db_rc = db_note_create(user_id, title, content);
    if (db_rc != 0) {
        return -1;
    }

    // 获取刚创建的笔记ID
    char sql[256];
    snprintf(sql, sizeof(sql), "SELECT last_insert_rowid()");
    sqlite3* db = db_get_connection();
    sqlite3_stmt* stmt;
    *note_id = 0;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            *note_id = sqlite3_column_int(stmt, 0);
        }
        sqlite3_finalize(stmt);
    }

    return 0;
}

// 更新笔记
int note_update_note(int note_id, const char* title, const char* content) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.note_id = note_id;
    strncpy(request.title, title, sizeof(request.title) - 1);
    strncpy(request.content, content, sizeof(request.content) - 1);
    request.op = RPC_UPDATE_NOTE;

    int rc = rpc_call(RPC_UPDATE_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        return 0;
    }
    return db_note_update(note_id, title, content);
}

// 删除笔记
int note_delete_note(int note_id) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.note_id = note_id;
    request.op = RPC_DELETE_NOTE;

    int rc = rpc_call(RPC_DELETE_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        return 0;
    }
    return db_note_delete(note_id);
}

// 恢复笔记
int note_restore_note(int note_id) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.note_id = note_id;
    request.op = RPC_RESTORE_NOTE;

    int rc = rpc_call(RPC_RESTORE_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        return 0;
    }
    return db_note_restore(note_id);
}

// 永久删除笔记
int note_force_delete_note(int note_id) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.note_id = note_id;
    request.op = RPC_FORCE_DELETE_NOTE;

    int rc = rpc_call(RPC_FORCE_DELETE_NOTE, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        return 0;
    }
    return db_note_force_delete(note_id);
}

// 获取FTP配置
int note_get_ftp_config(int user_id, FtpConfig* config) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    request.op = RPC_GET_FTP_CONFIG;

    int rc = rpc_call(RPC_GET_FTP_CONFIG, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        config->ftp_port = response.ftp_port;
        strncpy(config->ftp_host, response.ftp_host, sizeof(config->ftp_host) - 1);
        strncpy(config->ftp_user, response.ftp_user, sizeof(config->ftp_user) - 1);
        strncpy(config->ftp_path, response.ftp_path, sizeof(config->ftp_path) - 1);
        return 0;
    }
    return db_ftp_config_get_by_user(user_id, config);
}

// 保存FTP配置
int note_save_ftp_config(int user_id, const char* host, int port, const char* user, const char* pass, const char* path) {
    rpc_request_t request = {0};
    rpc_response_t response = {0};

    request.user_id = user_id;
    request.ftp_port = port;
    strncpy(request.ftp_host, host, sizeof(request.ftp_host) - 1);
    strncpy(request.ftp_user, user, sizeof(request.ftp_user) - 1);
    strncpy(request.ftp_pass, pass, sizeof(request.ftp_pass) - 1);
    strncpy(request.ftp_path, path, sizeof(request.ftp_path) - 1);
    request.op = RPC_UPDATE_FTP_CONFIG;

    int rc = rpc_call(RPC_UPDATE_FTP_CONFIG, &request, &response);
    if (rc == 0 && response.status == RPC_SUCCESS) {
        return 0;
    }
    return db_ftp_config_update(user_id, host, port, user, pass, path);
}

// 上传笔记到FTP
int note_upload_notes_to_ftp(int user_id, const char* host, const char* path) {
    FtpConfig config;
    int rc = db_ftp_config_get_by_user(user_id, &config);
    if (rc != 0) {
        return -1;
    }

    // 漏洞点：这里用system拼接IP做ping测试
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "ping -c 1 %s > /dev/null 2>&1 && echo OK", host);

    // 命令注入漏洞点
    int ping_result = system(cmd);

    if (ping_result != 0) {
        return -2;
    }

    return 0;
}
