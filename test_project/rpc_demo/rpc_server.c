/*
 * rpc_server.c - RPC 服务器端实现
 *
 * 作为接收端，处理来自 Web 服务器的消息
 * 完成消息接收、解析、业务分发
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>
#include "rpc.h"

/* 业务处理函数声明 */
extern int handle_login(rpc_login_req_t *req, uint32_t *auth_token);
extern int handle_data_packet(rpc_data_packet_t *packet, uint8_t *response, size_t *response_len);
extern int handle_heartbeat(void);

/* 内部消息处理函数声明 */
static int handle_login_msg(const uint8_t *request, size_t request_len,
                            uint8_t *response, size_t *response_len);
static int handle_data_msg(const uint8_t *request, size_t request_len,
                           uint8_t *response, size_t *response_len);
static int handle_heartbeat_msg(const uint8_t *request, size_t request_len,
                                uint8_t *response, size_t *response_len);

/* 序列化函数声明 */
extern size_t rpc_serialize_login_resp(const rpc_login_resp_t *resp, uint8_t *buffer, size_t buffer_size);

/* 全局状态 */
static uint32_t g_server_id = 1;
static uint32_t g_next_msg_id = 1;

/* 消息处理函数类型 */
typedef int (*msg_handler_t)(const uint8_t *request, size_t request_len,
                             uint8_t *response, size_t *response_len);

/* 消息处理表 */
static msg_handler_t g_msg_handlers[256] = {0};

/* 初始化消息处理表 */
static void init_msg_handlers(void)
{
    g_msg_handlers[RPC_MSG_LOGIN] = handle_login_msg;
    g_msg_handlers[RPC_MSG_DATA] = handle_data_msg;
    g_msg_handlers[RPC_MSG_HEARTBEAT] = handle_heartbeat_msg;
}

/*
 * 处理登录请求
 */
static int handle_login_msg(const uint8_t *request, size_t request_len,
                            uint8_t *response, size_t *response_len)
{
    rpc_login_req_t req;
    rpc_login_resp_t resp;
    rpc_header_t header;
    uint8_t buffer[256];
    size_t len;

    /* 解析请求头 */
    if (rpc_deserialize_header(request, request_len, &header) != 0) {
        return -1;
    }

    /* 解析登录请求数据 */
    if (header.payload_len < sizeof(rpc_login_req_t)) {
        return -1;
    }

    memcpy(&req, request + sizeof(rpc_header_t), sizeof(rpc_login_req_t));

    /* 调用业务处理 */
    int ret = handle_login(&req, &resp.auth_token);
    if (ret != 0) {
        resp.server_id = g_server_id;
        resp.auth_token = 0;
        resp.max_payload_size = 65536;
    } else {
        resp.server_id = g_server_id;
        resp.auth_token = req.client_id ^ 0xDEADBEEF;  /* 简单认证 */
        resp.max_payload_size = 65536;
    }

    /* 序列化响应 */
    len = rpc_serialize_login_resp(&resp, buffer, sizeof(buffer));

    /* 构建响应头 */
    rpc_header_t resp_header = {
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_RESPONSE,
        .msg_type = RPC_MSG_RESPONSE,
        .msg_id = header.msg_id,
        .payload_len = len
    };

    /* 序列化完整消息 */
    size_t total_len = rpc_serialize_header(&resp_header, response, *response_len);
    if (total_len + len > *response_len) {
        return -1;
    }
    memcpy(response + total_len, buffer, len);
    *response_len = total_len + len;

    return 0;
}

/*
 * 处理数据传输请求
 */
static int handle_data_msg(const uint8_t *request, size_t request_len,
                           uint8_t *response, size_t *response_len)
{
    rpc_data_packet_t *packet;
    uint8_t response_data[256];
    size_t response_data_len = 0;
    rpc_header_t header;
    uint8_t buffer[512];
    size_t len;

    /* 解析请求头 */
    if (rpc_deserialize_header(request, request_len, &header) != 0) {
        return -1;
    }

    /* 解析数据包 */
    if (header.payload_len < sizeof(rpc_data_packet_t)) {
        return -1;
    }

    packet = (rpc_data_packet_t*)(request + sizeof(rpc_header_t));

    /* 调用业务处理 */
    int ret = handle_data_packet(packet, response_data, &response_data_len);

    /* 构建响应 */
    rpc_response_t resp = {
        .original_msg_id = header.msg_id,
        .error_code = ret,
        .response_data_len = response_data_len
    };

    /* 序列化响应 */
    len = sizeof(rpc_response_t) + response_data_len;
    if (len > sizeof(buffer)) {
        return -1;
    }
    memcpy(buffer, &resp, sizeof(rpc_response_t));
    if (response_data_len > 0) {
        memcpy(buffer + sizeof(rpc_response_t), response_data, response_data_len);
    }

    /* 构建完整响应消息 */
    rpc_header_t resp_header = {
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_RESPONSE,
        .msg_type = RPC_MSG_RESPONSE,
        .msg_id = header.msg_id,
        .payload_len = len
    };

    size_t total_len = rpc_serialize_header(&resp_header, response, *response_len);
    if (total_len + len > *response_len) {
        return -1;
    }
    memcpy(response + total_len, buffer, len);
    *response_len = total_len + len;

    return 0;
}

/*
 * 处理心跳请求
 */
static int handle_heartbeat_msg(const uint8_t *request, size_t request_len,
                                uint8_t *response, size_t *response_len)
{
    rpc_header_t header;
    rpc_header_t resp_header;

    /* 解析请求头 */
    if (rpc_deserialize_header(request, request_len, &header) != 0) {
        return -1;
    }

    /* 构建空响应 */
    resp_header = (rpc_header_t){
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_RESPONSE,
        .msg_type = RPC_MSG_RESPONSE,
        .msg_id = header.msg_id,
        .payload_len = 0
    };

    *response_len = rpc_serialize_header(&resp_header, response, *response_len);
    return 0;
}

/*
 * 接收并处理消息的主循环
 * 这个函数模拟从 Web 服务器接收消息
 */
int rpc_server_process(int sock_fd, uint8_t *buffer, size_t buffer_size)
{
    rpc_header_t header;
    size_t bytes_read;
    size_t total_len;
    int ret;

    /* 步骤1: 先读取固定长度的头部 */
    bytes_read = read(sock_fd, buffer, sizeof(rpc_header_t));
    if (bytes_read != sizeof(rpc_header_t)) {
        fprintf(stderr, "Failed to read RPC header: %s\n", strerror(errno));
        return -1;
    }

    /* 步骤2: 反序列化头部 */
    if (rpc_deserialize_header(buffer, sizeof(rpc_header_t), &header) != 0) {
        fprintf(stderr, "Failed to deserialize header\n");
        return -1;
    }

    /* 验证魔数 */
    if (header.magic != RPC_MAGIC_NUMBER) {
        fprintf(stderr, "Invalid magic number: 0x%08X\n", header.magic);
        return -1;
    }

    printf("[RPC Server] Received message: type=%s, id=%u, payload_len=%u\n",
           rpc_msg_type_str(header.msg_type), header.msg_id, header.payload_len);

    /* 步骤3: 读取负载数据 */
    if (header.payload_len > buffer_size - sizeof(rpc_header_t)) {
        fprintf(stderr, "Payload too large\n");
        return -1;
    }

    if (header.payload_len > 0) {
        bytes_read = read(sock_fd, buffer + sizeof(rpc_header_t), header.payload_len);
        if (bytes_read != header.payload_len) {
            fprintf(stderr, "Failed to read payload: %s\n", strerror(errno));
            return -1;
        }
    }

    total_len = sizeof(rpc_header_t) + header.payload_len;

    /* 步骤4: 调用相应的消息处理函数 */
    if (header.msg_type < sizeof(g_msg_handlers) / sizeof(g_msg_handlers[0])
        && g_msg_handlers[header.msg_type] != NULL) {

        size_t response_len = buffer_size;
        ret = g_msg_handlers[header.msg_type](buffer, total_len, buffer, &response_len);

        if (ret == 0) {
            /* 步骤5: 发送响应 */
            printf("[RPC Server] Sending response, length=%zu\n", response_len);
            ssize_t written = write(sock_fd, buffer, response_len);
            if (written != (ssize_t)response_len) {
                fprintf(stderr, "Failed to send response: %s\n", strerror(errno));
                return -1;
            }
        }
        return ret;
    } else {
        fprintf(stderr, "Unknown message type: %u\n", header.msg_type);
        return -1;
    }
}

/*
 * 模拟服务器启动
 */
int rpc_server_start(const char *listen_addr, int port)
{
    printf("[RPC Server] Starting server on %s:%d\n", listen_addr, port);
    printf("[RPC Server] Waiting for connections from Web Server...\n");

    /* 初始化处理表 */
    init_msg_handlers();

    /* 这里应该是 socket bind listen 的实际代码 */
    /* 为演示目的，我们使用文件描述符 0 (stdin) 作为示例 */

    uint8_t buffer[4096];

    printf("[RPC Server] Enter test mode, type 'quit' to exit\n");

    while (1) {
        printf("[RPC Server] Waiting for message...\n");

        /* 模拟接收消息 */
        printf("[RPC Server] (In real code, this would read from socket)\n");

        /* 调用处理函数 */
        int ret = rpc_server_process(0, buffer, sizeof(buffer));
        if (ret != 0) {
            fprintf(stderr, "Error processing message: %d\n", ret);
        }
    }

    return 0;
}
