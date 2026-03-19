/**
 * 笔记业务逻辑模块
 */
#ifndef NOTE_LOGIC_H
#define NOTE_LOGIC_H

#include "db.h"
#include "rpc.h"

// 登录状态
typedef struct {
    int is_logged_in;
    int user_id;
    char username[128];
} LoginStatus;

// 初始化业务逻辑
int note_logic_init(void);

// 登录处理
int note_login(const char* username, const char* password, LoginStatus* status);

// 注册处理
int note_register(const char* username, const char* password, const char* email, LoginStatus* status);

// 获取用户笔记列表
int note_get_user_notes(int user_id, Note* notes, int* count, int max_count);

// 获取单个笔记
int note_get_note(int note_id, Note* note);

// 创建笔记
int note_create_note(int user_id, const char* title, const char* content, int* note_id);

// 更新笔记
int note_update_note(int note_id, const char* title, const char* content);

// 删除笔记
int note_delete_note(int note_id);

// 恢复笔记
int note_restore_note(int note_id);

// 永久删除笔记
int note_force_delete_note(int note_id);

// 获取FTP配置
int note_get_ftp_config(int user_id, FtpConfig* config);

// 保存FTP配置
int note_save_ftp_config(int user_id, const char* host, int port, const char* user, const char* pass, const char* path);

// 上传笔记到FTP
int note_upload_notes_to_ftp(int user_id, const char* host, const char* path);

// 重置密码（用于忘记密码功能）
int note_reset_password(int user_id, const char* new_password);

#endif /* NOTE_LOGIC_H */
