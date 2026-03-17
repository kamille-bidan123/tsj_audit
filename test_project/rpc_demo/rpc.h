/*
 * rpc.h - RPC 通信协议定义
 *
 * 定义 RPC 消息格式、消息类型和错误码
 * 用于 Web 服务器与业务处理进程间的通信
 */

#ifndef RPC_H
#define RPC_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 魔数，用于验证消息格式 */
#define RPC_MAGIC_NUMBER 0x52504300

/* 协议版本 */
#define RPC_VERSION 1

/* 消息类型 */
typedef enum {
    RPC_MSG_LOGIN      = 0x0001,  /* 登录请求 */
    RPC_MSG_DATA       = 0x0002,  /* 数据传输 */
    RPC_MSG_RESPONSE   = 0x0003,  /* 响应消息 */
    RPC_MSG_HEARTBEAT  = 0x0004,  /* 心跳包 */
    RPC_MSG_LOGOUT     = 0x0005,  /* 登出 */
} rpc_msg_type_t;

/* 错误码 */
typedef enum {
    RPC_ERR_SUCCESS       = 0,  /* 成功 */
    RPC_ERR_INVALID_MSG   = 1,  /* 无效消息 */
    RPC_ERR_AUTH_FAILED   = 2,  /* 认证失败 */
    RPC_ERR_TIMEOUT       = 3,  /* 超时 */
    RPC_ERR_UNKNOWN_TYPE  = 4,  /* 未知消息类型 */
    RPC_ERR_BUFFER_TOO_SMALL = 5, /* 缓冲区太小 */
} rpc_error_t;

/* 消息Flags */
#define RPC_FLAG_REQUEST    0x01
#define RPC_FLAG_RESPONSE   0x02

/* RPC 消息头 (固定 16 字节) */
typedef struct __attribute__((packed)) {
    uint32_t magic;       /* 魔数: 0x52504300 */
    uint8_t version;      /* 协议版本 */
    uint8_t flags;        /* 标志位 */
    uint16_t msg_type;    /* 消息类型 */
    uint32_t msg_id;      /* 消息ID/事务ID */
    uint32_t payload_len; /* 负载长度 */
} rpc_header_t;

/* RPC 消息体 */
typedef struct __attribute__((packed)) {
    uint32_t source_id;   /* 源地址ID */
    uint32_t target_id;   /* 目标地址ID */
    uint16_t port;        /* 端口号 */
    uint16_t command;     /* 命令码 */
    uint8_t data[];       /* 实际数据 (可变长度) */
} rpc_payload_t;

/* 登录请求数据 */
typedef struct {
    uint32_t client_id;
    char client_name[32];
    uint32_t capability;
} rpc_login_req_t;

/* 登录响应数据 */
typedef struct {
    uint32_t server_id;
    uint32_t auth_token;
    uint32_t max_payload_size;
} rpc_login_resp_t;

/* 通用数据包 */
typedef struct {
    uint32_t request_id;  /* 请求ID，用于匹配响应 */
    uint16_t data_type;   /* 数据类型 */
    uint16_t data_len;    /* 数据长度 */
    uint8_t data[];       /* 数据内容 */
} rpc_data_packet_t;

/* 响应消息 */
typedef struct {
    uint32_t original_msg_id;  /* 原始请求消息ID */
    uint16_t error_code;       /* 错误码 */
    uint16_t response_data_len;
    uint8_t response_data[];
} rpc_response_t;

/* 消息总长度计算 */
#define RPC_MSG_TOTAL_LEN(payload_len) \
    (sizeof(rpc_header_t) + (payload_len))

/* 协议大小检查 */
typedef char rpc_header_size_check[
    sizeof(rpc_header_t) == 16 ? 1 : -1
];

/* 函数声明 */

/*
 * 序列化函数：将消息结构转为字节流
 */
size_t rpc_serialize_header(const rpc_header_t *header, uint8_t *buffer, size_t buffer_size);

size_t rpc_serialize_login_req(const rpc_login_req_t *req, uint8_t *buffer, size_t buffer_size);

size_t rpc_serialize_data_packet(const rpc_data_packet_t *packet, uint8_t *buffer, size_t buffer_size);

/*
 * 反序列化函数：将字节流转为消息结构
 */
int rpc_deserialize_header(const uint8_t *buffer, size_t buffer_size, rpc_header_t *header);

int rpc_deserialize_login_resp(const uint8_t *buffer, size_t buffer_size, rpc_login_resp_t *resp);

int rpc_deserialize_response(const uint8_t *buffer, size_t buffer_size, rpc_response_t *resp);

/*
 * 网络字节序转换辅助函数
 */
void rpc_hton_header(rpc_header_t *header);
void rpc_ntoh_header(rpc_header_t *header);

/*
 * 工具函数
 */
const char* rpc_msg_type_str(uint16_t msg_type);
const char* rpc_error_str(uint16_t error_code);
uint32_t rpc_calc_checksum(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* RPC_H */
