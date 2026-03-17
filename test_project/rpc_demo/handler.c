/*
 * handler.c - 业务处理函数实现
 *
 * 实际的业务逻辑处理，由 RPC 服务器调用
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rpc.h"

/*
 * 处理登录请求
 */
int handle_login(rpc_login_req_t *req, uint32_t *auth_token)
{
    printf("[Handler] Handling LOGIN request from client %u (%s)\n",
           req->client_id, req->client_name);

    /* 这里进行实际的认证逻辑 */
    /* 验证客户端身份、权限等 */

    /* 生成认证令牌 */
    *auth_token = req->client_id ^ 0x12345678;

    printf("[Handler] Login successful, auth_token=0x%08X\n", *auth_token);

    return 0;
}

/*
 * 处理数据包
 * 这个函数执行实际的业务逻辑
 */
int handle_data_packet(rpc_data_packet_t *packet, uint8_t *response, size_t *response_len)
{
    printf("[Handler] Handling DATA packet:\n");
    printf("  request_id: %u\n", packet->request_id);
    printf("  data_type: %u\n", packet->data_type);
    printf("  data_len: %u\n", packet->data_len);
    printf("  data: %.*s\n", (int)packet->data_len, packet->data);

    /* 这里进行实际的业务处理 */
    /* 例如：查询数据库、处理业务逻辑等 */

    /* 构建响应数据 */
    const char *result = "OK: Request processed successfully";
    size_t result_len = strlen(result);

    if (result_len + sizeof(rpc_response_t) > 256) {
        return -1;
    }

    /* 填充响应 */
    rpc_response_t *resp = (rpc_response_t*)response;
    resp->original_msg_id = packet->request_id;
    resp->error_code = 0;
    resp->response_data_len = (uint16_t)result_len;
    memcpy(resp->response_data, result, result_len);

    *response_len = sizeof(rpc_response_t) + result_len;

    printf("[Handler] Response generated, length=%zu\n", *response_len);

    return 0;
}

/*
 * 处理心跳包
 */
int handle_heartbeat(void)
{
    printf("[Handler] Handling HEARTBEAT\n");
    return 0;
}

/*
 * 模拟业务处理
 */
void process_business_logic(const uint8_t *data, size_t len, uint8_t *output, size_t *output_len)
{
    printf("[Business Logic] Processing: %.*s\n", (int)len, data);

    /* 模拟业务处理 */
    *output_len = snprintf((char*)output, 256, "Processed: %.*s", (int)len, data);
}
