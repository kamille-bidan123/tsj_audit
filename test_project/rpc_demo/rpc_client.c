/*
 * rpc_client.c - RPC 客户端实现
 *
 * 作为发送端，Web 服务器将接收到的请求发送给业务处理进程
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include "rpc.h"

/* 全局状态 */
static uint32_t g_client_id = 100;
static uint32_t g_next_msg_id = 1;
static uint32_t g_auth_token = 0;

/*
 * 生成下一个消息ID
 */
static uint32_t next_msg_id(void)
{
    return g_next_msg_id++;
}

/*
 * 发送登录请求
 */
int rpc_client_login(const char *client_name, uint32_t *auth_token)
{
    uint8_t request[256];
    uint8_t response[256];
    size_t request_len;
    size_t response_len;

    /* 构建登录请求数据 */
    rpc_login_req_t login_req = {
        .client_id = g_client_id,
        .capability = 1
    };
    strncpy(login_req.client_name, client_name, sizeof(login_req.client_name) - 1);
    login_req.client_name[sizeof(login_req.client_name) - 1] = '\0';

    /* 序列化登录请求数据 */
    request_len = rpc_serialize_login_req(&login_req, request + sizeof(rpc_header_t),
                                          sizeof(request) - sizeof(rpc_header_t));

    /* 构建请求头 */
    rpc_header_t header = {
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_REQUEST,
        .msg_type = RPC_MSG_LOGIN,
        .msg_id = next_msg_id(),
        .payload_len = request_len
    };

    /* 序列化头部到缓冲区开头 */
    size_t header_len = rpc_serialize_header(&header, request, sizeof(request));
    if (header_len != sizeof(rpc_header_t)) {
        return -1;
    }

    request_len += header_len;

    printf("[RPC Client] Sending LOGIN request, msg_id=%u\n", header.msg_id);

    /* 发送请求 (这里应该是 send/Socket send) */
    /* ssize_t sent = send(sock_fd, request, request_len, 0); */

    /* 模拟接收响应 */
    response_len = sizeof(rpc_header_t) + sizeof(rpc_login_resp_t);
    rpc_login_resp_t resp;
    resp.server_id = 1;
    resp.auth_token = login_req.client_id ^ 0xDEADBEEF;  /* 模拟认证成功 */
    resp.max_payload_size = 65536;

    /* 验证响应 */
    if (resp.auth_token != 0) {
        g_auth_token = resp.auth_token;
        printf("[RPC Client] Login successful, auth_token=0x%08X\n", g_auth_token);
        if (auth_token) {
            *auth_token = g_auth_token;
        }
        return 0;
    }

    return -1;
}

/*
 * 发送数据包
 * 这个函数在 Web 服务器接收到外部请求后调用
 */
int rpc_client_send_data(uint16_t data_type, const uint8_t *data, size_t data_len,
                         uint8_t *response, size_t *response_len)
{
    uint8_t request[1024];
    size_t request_len;

    /* 构建数据包 */
    rpc_data_packet_t *packet = (rpc_data_packet_t*)(request + sizeof(rpc_header_t));
    packet->request_id = next_msg_id();
    packet->data_type = data_type;
    packet->data_len = (uint16_t)data_len;
    memcpy(packet->data, data, data_len);

    /* 计算总负载长度 */
    size_t payload_len = sizeof(rpc_data_packet_t) + data_len;

    /* 构建请求头 */
    rpc_header_t header = {
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_REQUEST,
        .msg_type = RPC_MSG_DATA,
        .msg_id = packet->request_id,
        .payload_len = (uint32_t)payload_len
    };

    /* 序列化头部 */
    request_len = rpc_serialize_header(&header, request, sizeof(request));
    if (request_len != sizeof(rpc_header_t)) {
        return -1;
    }

    /* 将数据包复制到头部后面 */
    memcpy(request + request_len, packet, payload_len);
    request_len += payload_len;

    printf("[RPC Client] Sending DATA request, msg_id=%u, data_type=%u, len=%zu\n",
           header.msg_id, data_type, data_len);

    /* 发送请求 */
    /* ssize_t sent = send(sock_fd, request, request_len, 0); */

    /* 模拟处理 */
    if (response && response_len) {
        /* 构建模拟响应 */
        rpc_response_t *resp = (rpc_response_t*)response;
        resp->original_msg_id = header.msg_id;
        resp->error_code = 0;  /* 成功 */
        resp->response_data_len = 0;
        *response_len = sizeof(rpc_response_t);
    }

    return 0;
}

/*
 * 发送心跳包
 */
int rpc_client_heartbeat(void)
{
    uint8_t request[64];
    size_t request_len;

    /* 构建心跳请求头 */
    rpc_header_t header = {
        .magic = RPC_MAGIC_NUMBER,
        .version = RPC_VERSION,
        .flags = RPC_FLAG_REQUEST,
        .msg_type = RPC_MSG_HEARTBEAT,
        .msg_id = next_msg_id(),
        .payload_len = 0
    };

    request_len = rpc_serialize_header(&header, request, sizeof(request));

    printf("[RPC Client] Sending HEARTBEAT, msg_id=%u\n", header.msg_id);

    /* 发送请求 */
    /* ssize_t sent = send(sock_fd, request, request_len, 0); */

    return 0;
}

/*
 * 初始化客户端
 */
int rpc_client_init(uint32_t client_id, const char *server_addr, int server_port)
{
    g_client_id = client_id;
    printf("[RPC Client] Initialized: id=%u, server=%s:%d\n",
           client_id, server_addr, server_port);
    return 0;
}

/*
 * 模拟 Web 服务器处理流程
 * 这个函数演示了 Web 服务器如何接收请求，然后通过 RPC 发送给业务进程
 */
int web_server_handle_request(const char *client_data, size_t data_len,
                              char *response, size_t *response_len)
{
    uint8_t rpc_response[256];
    size_t rpc_response_len;
    uint8_t data_buffer[256];

    printf("\n=== Web Server Handling Request ===\n");

    /* 步骤1: Web 服务器接收到客户端请求 */
    printf("[Web Server] Received client request: %.*s\n", (int)data_len, client_data);

    /* 步骤2: 解析客户端请求，准备要发送给业务进程的数据 */
    size_t packed_len = snprintf((char*)data_buffer, sizeof(data_buffer),
                                  "_client_request_%s", client_data);

    /* 步骤3: 通过 RPC 发送给业务处理进程 */
    int ret = rpc_client_send_data(1, data_buffer, packed_len, rpc_response, &rpc_response_len);

    if (ret != 0) {
        printf("[Web Server] RPC send failed\n");
        return -1;
    }

    /* 步骤4: 解析业务进程的响应 */
    if (rpc_response_len >= sizeof(rpc_response_t)) {
        rpc_response_t *resp = (rpc_response_t*)rpc_response;
        printf("[Web Server] Received RPC response: msg_id=%u, error=%u\n",
               resp->original_msg_id, resp->error_code);
    }

    /* 步骤5: 构建返回给客户端的响应 */
    *response_len = snprintf(response, *response_len,
                             "Processed by RPC server: %s", client_data);

    printf("[Web Server] Sending response to client\n");
    printf("=====================================\n\n");

    return 0;
}

/*
 * 主函数：演示完整的 Web -> RPC 流程
 */
int main(int argc, char *argv[])
{
    uint32_t auth_token;
    char response[256];
    size_t response_len;

    printf("=== RPC Client Demo ===\n\n");

    /* 初始化客户端 */
    rpc_client_init(100, "127.0.0.1", 8080);

    /* 步骤1: 登录到 RPC 服务器 */
    printf("\n[Step 1] Logging in to RPC server...\n");
    rpc_client_login("web_server", &auth_token);

    /* 步骤2: 模拟处理客户端请求 */
    printf("\n[Step 2] Handling client request via RPC...\n");
    const char *client_request = "GET /api/user?id=123 HTTP/1.1";
    response_len = sizeof(response);
    web_server_handle_request(client_request, strlen(client_request),
                              response, &response_len);
    printf("Response: %s\n", response);

    /* 步骤3: 发送心跳 */
    printf("\n[Step 3] Sending heartbeat...\n");
    rpc_client_heartbeat();

    printf("\n=== Demo Complete ===\n");

    return 0;
}
