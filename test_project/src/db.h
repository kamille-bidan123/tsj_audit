/**
 * 数据库模块 - 记事本应用的SQLite数据库操作
 */
#ifndef DB_H
#define DB_H

#include <sqlite3.h>
#include <string.h>

#define DB_PATH "./notes.db"
#define MAX_USER_LEN 128
#define MAX_NOTE_TITLE_LEN 256
#define MAX_NOTE_CONTENT_LEN 65536
#define MAX_FTP_CONFIG_LEN 512

// 用户表
typedef struct {
    int id;
    char username[MAX_USER_LEN];
    char password_hash[65];  // SHA256 hex
    char email[128];
    int login_fail_count;
    int last_fail_time;
    int is_locked;
    char created_at[32];
} User;

// 笔记表
typedef struct {
    int id;
    int user_id;
    char title[MAX_NOTE_TITLE_LEN];
    char content[MAX_NOTE_CONTENT_LEN];
    int is_deleted;
    char created_at[32];
    char updated_at[32];
} Note;

// FTP配置表
typedef struct {
    int id;
    int user_id;
    char ftp_host[256];
    int ftp_port;
    char ftp_user[128];
    char ftp_pass[128];
    char ftp_path[256];
    char created_at[32];
} FtpConfig;

// 初始化数据库
int db_init(void);

// 关闭数据库
void db_close(void);

// 获取数据库连接
sqlite3* db_get_connection(void);

// 用户相关操作
int db_user_create(const char* username, const char* password_hash, const char* email);
int db_user_get_by_username(const char* username, User* user);
int db_user_get_by_id(int id, User* user);
int db_user_update_password(int user_id, const char* new_hash);
int db_user_increment_login_fail(int user_id);
int db_user_reset_login_fail(int user_id);
int db_user_lock(int user_id);
int db_user_unlock(int user_id);
int db_user_is_locked(int user_id);
int db_user_check_login_fail_limit(int user_id);

// 笔记相关操作
int db_note_create(int user_id, const char* title, const char* content);
int db_note_get_by_id(int note_id, Note* note);
int db_note_get_by_user(int user_id, Note* notes, int* count, int max_count);
int db_note_update(int note_id, const char* title, const char* content);
int db_note_delete(int note_id);
int db_note_restore(int note_id);
int db_note_force_delete(int note_id);

// FTP配置相关操作
int db_ftp_config_create(int user_id, const char* host, int port, const char* user, const char* pass, const char* path);
int db_ftp_config_get_by_user(int user_id, FtpConfig* config);
int db_ftp_config_update(int user_id, const char* host, int port, const char* user, const char* pass, const char* path);

// 检查用户是否存在
int db_user_exists(const char* username);

#endif /* DB_H */
