/**
 * RPC 模块 - 进程间通信
 * 使用命名管道(FIFO)实现Web进程和Worker进程之间的通信
 */
#ifndef RPC_H
#define RPC_H

#include <stdint.h>
#include <stddef.h>

// RPC 操作码
typedef enum {
    RPC_PING = 0,
    RPC_LOGIN,
    RPC_REGISTER,
    RPC_GET_NOTES,
    RPC_GET_NOTE,
    RPC_CREATE_NOTE,
    RPC_UPDATE_NOTE,
    RPC_DELETE_NOTE,
    RPC_RESTORE_NOTE,
    RPC_GET_FTP_CONFIG,
    RPC_UPDATE_FTP_CONFIG,
    RPC_UPLOAD_NOTES_TO_FTP,
    RPC_FORCE_DELETE_NOTE,
    RPC_LAST_OP
} rpc_op_t;

// RPC 请求类型
typedef struct {
    uint32_t op;           // 操作码
    uint32_t request_id;   // 请求ID
    uint32_t user_id;      // 用户ID
    uint32_t note_id;      // 笔记ID
    uint32_t is_deleted;   // 是否删除
    char username[128];    // 用户名
    char password[65];     // 密码哈希
    char email[128];       // 邮箱
    char title[256];       // 标题
    char content[65536];   // 内容
    int ftp_port;          // FTP端口
    char ftp_host[256];    // FTP主机
    char ftp_user[128];    // FTP用户名
    char ftp_pass[128];    // FTP密码
    char ftp_path[256];    // FTP路径
} rpc_request_t;

// RPC 响应类型
typedef struct {
    uint32_t request_id;   // 请求ID
    int32_t status;        // 状态码: 0=成功, -1=失败, 其他=错误码
    char message[256];     // 响应消息
    uint32_t user_id;      // 用户ID
    uint32_t note_id;      // 笔记ID
    uint32_t note_count;   // 笔记数量
    char notes_data[65536];// 笔记数据(JSON格式)
    char ftp_host[256];    // FTP主机
    int ftp_port;          // FTP端口
    char ftp_user[128];    // FTP用户名
    char ftp_path[256];    // FTP路径
} rpc_response_t;

// RPC 通信路径
#define RPC_PIPE_PATH "./rpc_pipe"
#define RPC_RESPONSE_PATH "./rpc_response"

// RPC 错误码
#define RPC_SUCCESS 0
#define RPC_ERROR_INTERNAL -1
#define RPC_ERROR_INVALID_PARAM -2
#define RPC_ERROR_NOT_FOUND -3
#define RPC_ERROR_FAILED -4

// 初始化 RPC
int rpc_init(void);

// 关闭 RPC
void rpc_close(void);

// 发送请求到 worker 进程
int rpc_send_request(const rpc_request_t* request, rpc_response_t* response);

// 处理 RPC 请求的回调函数类型
typedef int (*rpc_handler_t)(const rpc_request_t* request, rpc_response_t* response);

// 注册 RPC 处理器
int rpc_register_handler(uint32_t op, rpc_handler_t handler);

// 获取 RPC 请求数据长度
size_t rpc_get_request_size(const rpc_request_t* request);

// 获取 RPC 响应数据长度
size_t rpc_get_response_size(const rpc_response_t* response);

// 外部访问处理器数组（供worker进程使用）
extern rpc_handler_t g_handlers[RPC_LAST_OP];

#endif /* RPC_H */
