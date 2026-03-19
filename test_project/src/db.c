/**
 * 数据库模块实现
 */
#include "db.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

static sqlite3* g_db = NULL;

static const char* CREATE_TABLES_SQL[] = {
    // 用户表
    "CREATE TABLE IF NOT EXISTS users ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  username TEXT UNIQUE NOT NULL,"
    "  password_hash TEXT NOT NULL,"
    "  email TEXT,"
    "  login_fail_count INTEGER DEFAULT 0,"
    "  last_fail_time INTEGER DEFAULT 0,"
    "  is_locked INTEGER DEFAULT 0,"
    "  created_at TEXT"
    ");",

    // 笔记表
    "CREATE TABLE IF NOT EXISTS notes ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  user_id INTEGER NOT NULL,"
    "  title TEXT NOT NULL,"
    "  content TEXT,"
    "  is_deleted INTEGER DEFAULT 0,"
    "  created_at TEXT,"
    "  updated_at TEXT,"
    "  FOREIGN KEY (user_id) REFERENCES users(id)"
    ");",

    // FTP配置表
    "CREATE TABLE IF NOT EXISTS ftp_configs ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  user_id INTEGER UNIQUE NOT NULL,"
    "  ftp_host TEXT,"
    "  ftp_port INTEGER DEFAULT 21,"
    "  ftp_user TEXT,"
    "  ftp_pass TEXT,"
    "  ftp_path TEXT DEFAULT '/',"
    "  created_at TEXT,"
    "  FOREIGN KEY (user_id) REFERENCES users(id)"
    ");",

    // 插入测试用户
    "INSERT OR IGNORE INTO users (username, password_hash, email, created_at) "
    "VALUES ('admin', '5e884898da28047d915c47b8d2e4b9f8a3c9d1e7f6a5b4c3d2e1f0a9b8c7d6e5f4', 'admin@example.com', datetime('now'));"
};

static const char* SELECT_USER_BY_USERNAME =
    "SELECT id, username, password_hash, email, login_fail_count, last_fail_time, is_locked, created_at FROM users WHERE username = ?";

static const char* SELECT_USER_BY_ID =
    "SELECT id, username, password_hash, email, login_fail_count, last_fail_time, is_locked, created_at FROM users WHERE id = ?";

static const char* SELECT_NOTE_BY_ID =
    "SELECT id, user_id, title, content, is_deleted, created_at, updated_at FROM notes WHERE id = ?";

static const char* SELECT_NOTES_BY_USER =
    "SELECT id, user_id, title, content, is_deleted, created_at, updated_at FROM notes WHERE user_id = ? AND is_deleted = 0 ORDER BY updated_at DESC";

static const char* SELECT_FTP_BY_USER =
    "SELECT id, user_id, ftp_host, ftp_port, ftp_user, ftp_pass, ftp_path, created_at FROM ftp_configs WHERE user_id = ?";

static const char* INSERT_USER =
    "INSERT INTO users (username, password_hash, email, created_at) VALUES (?, ?, ?, ?)";

static const char* INSERT_NOTE =
    "INSERT INTO notes (user_id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)";

static const char* UPDATE_NOTE =
    "UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?";

static const char* UPDATE_USER_PASSWORD =
    "UPDATE users SET password_hash = ? WHERE id = ?";

static const char* UPDATE_FTP_CONFIG =
    "UPDATE ftp_configs SET ftp_host = ?, ftp_port = ?, ftp_user = ?, ftp_pass = ?, ftp_path = ? WHERE user_id = ?";

static const char* DELETE_NOTE =
    "UPDATE notes SET is_deleted = 1, updated_at = ? WHERE id = ?";

static const char* FORCE_DELETE_NOTE =
    "DELETE FROM notes WHERE id = ?";

static const char* INSERT_FTP_CONFIG =
    "INSERT INTO ftp_configs (user_id, ftp_host, ftp_port, ftp_user, ftp_pass, ftp_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)";

static const char* CHECK_USER_EXISTS =
    "SELECT COUNT(*) FROM users WHERE username = ?";

static const char* INCREMENT_LOGIN_FAIL =
    "UPDATE users SET login_fail_count = login_fail_count + 1, last_fail_time = ? WHERE id = ?";

static const char* RESET_LOGIN_FAIL =
    "UPDATE users SET login_fail_count = 0 WHERE id = ?";

static const char* LOCK_USER =
    "UPDATE users SET is_locked = 1 WHERE id = ?";

static const char* UNLOCK_USER =
    "UPDATE users SET is_locked = 0 WHERE id = ?";

static const char* CHECK_LOGIN_FAIL_LIMIT =
    "SELECT login_fail_count, last_fail_time FROM users WHERE id = ?";

static const char* CHECK_IF_LOCKED =
    "SELECT is_locked FROM users WHERE id = ?";

static void get_timestamp(char* buf, size_t size) {
    time_t now = time(NULL);
    struct tm* tm_info = localtime(&now);
    strftime(buf, size, "%Y-%m-%d %H:%M:%S", tm_info);
}

static int create_table(sqlite3* db, const char* sql) {
    char* err_msg = 0;
    int rc = sqlite3_exec(db, sql, NULL, 0, &err_msg);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "SQL error: %s\n", err_msg);
        sqlite3_free(err_msg);
        return -1;
    }
    return 0;
}

int db_init(void) {
    if (g_db != NULL) {
        return 0;
    }

    int rc = sqlite3_open(DB_PATH, &g_db);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "Cannot open database: %s\n", sqlite3_errmsg(g_db));
        return -1;
    }

    // 创建表
    for (size_t i = 0; i < sizeof(CREATE_TABLES_SQL) / sizeof(CREATE_TABLES_SQL[0]); i++) {
        if (create_table(g_db, CREATE_TABLES_SQL[i]) != 0) {
            return -1;
        }
    }

    fprintf(stderr, "[DB] Database initialized successfully\n");
    return 0;
}

void db_close(void) {
    if (g_db != NULL) {
        sqlite3_close(g_db);
        g_db = NULL;
    }
}

sqlite3* db_get_connection(void) {
    return g_db;
}

int db_user_exists(const char* username) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, CHECK_USER_EXISTS, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_text(stmt, 1, username, -1, NULL);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        int count = sqlite3_column_int(stmt, 0);
        sqlite3_finalize(stmt);
        return count > 0 ? 1 : 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_user_create(const char* username, const char* password_hash, const char* email) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, INSERT_USER, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_text(stmt, 1, username, -1, NULL);
    sqlite3_bind_text(stmt, 2, password_hash, -1, NULL);
    sqlite3_bind_text(stmt, 3, email ? email : "", -1, NULL);

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 4, timestamp, -1, NULL);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_get_by_username(const char* username, User* user) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, SELECT_USER_BY_USERNAME, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_text(stmt, 1, username, -1, NULL);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        user->id = sqlite3_column_int(stmt, 0);
        strncpy(user->username, (const char*)sqlite3_column_text(stmt, 1), MAX_USER_LEN - 1);
        strncpy(user->password_hash, (const char*)sqlite3_column_text(stmt, 2), 64);
        user->password_hash[64] = '\0';

        if (sqlite3_column_text(stmt, 3)) {
            strncpy(user->email, (const char*)sqlite3_column_text(stmt, 3), 127);
            user->email[127] = '\0';
        } else {
            user->email[0] = '\0';
        }

        user->login_fail_count = sqlite3_column_int(stmt, 4);
        user->last_fail_time = sqlite3_column_int(stmt, 5);
        user->is_locked = sqlite3_column_int(stmt, 6);

        if (sqlite3_column_text(stmt, 7)) {
            strncpy(user->created_at, (const char*)sqlite3_column_text(stmt, 7), 31);
            user->created_at[31] = '\0';
        } else {
            user->created_at[0] = '\0';
        }

        sqlite3_finalize(stmt);
        return 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_user_get_by_id(int id, User* user) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, SELECT_USER_BY_ID, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, id);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        user->id = sqlite3_column_int(stmt, 0);
        strncpy(user->username, (const char*)sqlite3_column_text(stmt, 1), MAX_USER_LEN - 1);
        strncpy(user->password_hash, (const char*)sqlite3_column_text(stmt, 2), 64);
        user->password_hash[64] = '\0';

        if (sqlite3_column_text(stmt, 3)) {
            strncpy(user->email, (const char*)sqlite3_column_text(stmt, 3), 127);
            user->email[127] = '\0';
        } else {
            user->email[0] = '\0';
        }

        user->login_fail_count = sqlite3_column_int(stmt, 4);
        user->last_fail_time = sqlite3_column_int(stmt, 5);
        user->is_locked = sqlite3_column_int(stmt, 6);

        if (sqlite3_column_text(stmt, 7)) {
            strncpy(user->created_at, (const char*)sqlite3_column_text(stmt, 7), 31);
            user->created_at[31] = '\0';
        } else {
            user->created_at[0] = '\0';
        }

        sqlite3_finalize(stmt);
        return 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_user_update_password(int user_id, const char* new_hash) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, UPDATE_USER_PASSWORD, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_text(stmt, 1, new_hash, -1, NULL);
    sqlite3_bind_int(stmt, 2, user_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_increment_login_fail(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, INCREMENT_LOGIN_FAIL, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    int now = (int)time(NULL);
    sqlite3_bind_int(stmt, 1, now);
    sqlite3_bind_int(stmt, 2, user_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_reset_login_fail(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, RESET_LOGIN_FAIL, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_lock(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, LOCK_USER, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_unlock(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, UNLOCK_USER, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_user_is_locked(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, CHECK_IF_LOCKED, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        int locked = sqlite3_column_int(stmt, 0);
        sqlite3_finalize(stmt);
        return locked;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_user_check_login_fail_limit(int user_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, CHECK_LOGIN_FAIL_LIMIT, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        int fail_count = sqlite3_column_int(stmt, 0);
        int last_fail = sqlite3_column_int(stmt, 1);
        sqlite3_finalize(stmt);

        // 3次失败后锁定5分钟
        if (fail_count >= 3) {
            int now = (int)time(NULL);
            if (now - last_fail < 300) {  // 5分钟
                return 1;  // 被锁定
            }
            // 超过5分钟，重置
            db_user_reset_login_fail(user_id);
            return 0;
        }
        return 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_note_create(int user_id, const char* title, const char* content) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, INSERT_NOTE, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);
    sqlite3_bind_text(stmt, 2, title, -1, NULL);
    sqlite3_bind_text(stmt, 3, content ? content : "", -1, NULL);

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 4, timestamp, -1, NULL);
    sqlite3_bind_text(stmt, 5, timestamp, -1, NULL);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_note_get_by_id(int note_id, Note* note) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, SELECT_NOTE_BY_ID, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, note_id);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        note->id = sqlite3_column_int(stmt, 0);
        note->user_id = sqlite3_column_int(stmt, 1);
        strncpy(note->title, (const char*)sqlite3_column_text(stmt, 2), MAX_NOTE_TITLE_LEN - 1);

        if (sqlite3_column_text(stmt, 3)) {
            strncpy(note->content, (const char*)sqlite3_column_text(stmt, 3), MAX_NOTE_CONTENT_LEN - 1);
        } else {
            note->content[0] = '\0';
        }

        note->is_deleted = sqlite3_column_int(stmt, 4);

        if (sqlite3_column_text(stmt, 5)) {
            strncpy(note->created_at, (const char*)sqlite3_column_text(stmt, 5), 31);
        } else {
            note->created_at[0] = '\0';
        }

        if (sqlite3_column_text(stmt, 6)) {
            strncpy(note->updated_at, (const char*)sqlite3_column_text(stmt, 6), 31);
        } else {
            note->updated_at[0] = '\0';
        }

        sqlite3_finalize(stmt);
        return 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_note_get_by_user(int user_id, Note* notes, int* count, int max_count) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, SELECT_NOTES_BY_USER, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    int i = 0;
    while (sqlite3_step(stmt) == SQLITE_ROW && i < max_count) {
        notes[i].id = sqlite3_column_int(stmt, 0);
        notes[i].user_id = sqlite3_column_int(stmt, 1);
        strncpy(notes[i].title, (const char*)sqlite3_column_text(stmt, 2), MAX_NOTE_TITLE_LEN - 1);

        if (sqlite3_column_text(stmt, 3)) {
            strncpy(notes[i].content, (const char*)sqlite3_column_text(stmt, 3), MAX_NOTE_CONTENT_LEN - 1);
        } else {
            notes[i].content[0] = '\0';
        }

        notes[i].is_deleted = sqlite3_column_int(stmt, 4);

        if (sqlite3_column_text(stmt, 5)) {
            strncpy(notes[i].created_at, (const char*)sqlite3_column_text(stmt, 5), 31);
        } else {
            notes[i].created_at[0] = '\0';
        }

        if (sqlite3_column_text(stmt, 6)) {
            strncpy(notes[i].updated_at, (const char*)sqlite3_column_text(stmt, 6), 31);
        } else {
            notes[i].updated_at[0] = '\0';
        }

        i++;
    }

    *count = i;
    sqlite3_finalize(stmt);
    return 0;
}

int db_note_update(int note_id, const char* title, const char* content) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, UPDATE_NOTE, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_text(stmt, 1, title, -1, NULL);
    sqlite3_bind_text(stmt, 2, content ? content : "", -1, NULL);

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 3, timestamp, -1, NULL);
    sqlite3_bind_int(stmt, 4, note_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_note_delete(int note_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, DELETE_NOTE, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 1, timestamp, -1, NULL);
    sqlite3_bind_int(stmt, 2, note_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_note_restore(int note_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, "UPDATE notes SET is_deleted = 0, updated_at = ? WHERE id = ?", -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 1, timestamp, -1, NULL);
    sqlite3_bind_int(stmt, 2, note_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_note_force_delete(int note_id) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, FORCE_DELETE_NOTE, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, note_id);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_ftp_config_create(int user_id, const char* host, int port, const char* user, const char* pass, const char* path) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, INSERT_FTP_CONFIG, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);
    sqlite3_bind_text(stmt, 2, host ? host : "", -1, NULL);
    sqlite3_bind_int(stmt, 3, port);
    sqlite3_bind_text(stmt, 4, user ? user : "", -1, NULL);
    sqlite3_bind_text(stmt, 5, pass ? pass : "", -1, NULL);
    sqlite3_bind_text(stmt, 6, path ? path : "/", -1, NULL);

    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    sqlite3_bind_text(stmt, 7, timestamp, -1, NULL);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    return (rc == SQLITE_DONE) ? 0 : -1;
}

int db_ftp_config_get_by_user(int user_id, FtpConfig* config) {
    if (g_db == NULL) return -1;

    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(g_db, SELECT_FTP_BY_USER, -1, &stmt, NULL);
    if (rc != SQLITE_OK) return -1;

    sqlite3_bind_int(stmt, 1, user_id);

    if (sqlite3_step(stmt) == SQLITE_ROW) {
        config->id = sqlite3_column_int(stmt, 0);
        config->user_id = sqlite3_column_int(stmt, 1);

        if (sqlite3_column_text(stmt, 2)) {
            strncpy(config->ftp_host, (const char*)sqlite3_column_text(stmt, 2), 255);
        } else {
            config->ftp_host[0] = '\0';
        }

        config->ftp_port = sqlite3_column_int(stmt, 3);

        if (sqlite3_column_text(stmt, 4)) {
            strncpy(config->ftp_user, (const char*)sqlite3_column_text(stmt, 4), 127);
        } else {
            config->ftp_user[0] = '\0';
        }

        if (sqlite3_column_text(stmt, 5)) {
            strncpy(config->ftp_pass, (const char*)sqlite3_column_text(stmt, 5), 127);
        } else {
            config->ftp_pass[0] = '\0';
        }

        if (sqlite3_column_text(stmt, 6)) {
            strncpy(config->ftp_path, (const char*)sqlite3_column_text(stmt, 6), 255);
        } else {
            config->ftp_path[0] = '\0';
        }

        if (sqlite3_column_text(stmt, 7)) {
            strncpy(config->created_at, (const char*)sqlite3_column_text(stmt, 7), 31);
        } else {
            config->created_at[0] = '\0';
        }

        sqlite3_finalize(stmt);
        return 0;
    }

    sqlite3_finalize(stmt);
    return -1;
}

int db_ftp_config_update(int user_id, const char* host, int port, const char* user, const char* pass, const char* path) {
    if (g_db == NULL) return -1;

    FtpConfig existing;
    if (db_ftp_config_get_by_user(user_id, &existing) == 0) {
        // 已存在，更新
        sqlite3_stmt* stmt;
        int rc = sqlite3_prepare_v2(g_db, UPDATE_FTP_CONFIG, -1, &stmt, NULL);
        if (rc != SQLITE_OK) return -1;

        sqlite3_bind_text(stmt, 1, host ? host : "", -1, NULL);
        sqlite3_bind_int(stmt, 2, port);
        sqlite3_bind_text(stmt, 3, user ? user : "", -1, NULL);
        sqlite3_bind_text(stmt, 4, pass ? pass : "", -1, NULL);
        sqlite3_bind_text(stmt, 5, path ? path : "/", -1, NULL);
        sqlite3_bind_int(stmt, 6, user_id);

        rc = sqlite3_step(stmt);
        sqlite3_finalize(stmt);
        return (rc == SQLITE_DONE) ? 0 : -1;
    }

    // 不存在，插入
    return db_ftp_config_create(user_id, host, port, user, pass, path);
}
