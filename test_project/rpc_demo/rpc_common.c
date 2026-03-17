/*
 * rpc_common.c - RPC 公共实现
 *
 * 实现协议相关的通用函数
 */

#include <stdio.h>
#include <string.h>
#include <arpa/inet.h>
#include "rpc.h"

/*
 * 序列化头部
 */
size_t rpc_serialize_header(const rpc_header_t *header, uint8_t *buffer, size_t buffer_size)
{
    if (buffer_size < sizeof(rpc_header_t)) {
        return 0;
    }

    memcpy(buffer, header, sizeof(rpc_header_t));
    return sizeof(rpc_header_t);
}

/*
 * 序列化登录请求
 */
size_t rpc_serialize_login_req(const rpc_login_req_t *req, uint8_t *buffer, size_t buffer_size)
{
    if (buffer_size < sizeof(rpc_login_req_t)) {
        return 0;
    }

    memcpy(buffer, req, sizeof(rpc_login_req_t));
    return sizeof(rpc_login_req_t);
}

/*
 * 序列化登录响应
 */
size_t rpc_serialize_login_resp(const rpc_login_resp_t *resp, uint8_t *buffer, size_t buffer_size)
{
    if (buffer_size < sizeof(rpc_login_resp_t)) {
        return 0;
    }

    memcpy(buffer, resp, sizeof(rpc_login_resp_t));
    return sizeof(rpc_login_resp_t);
}

/*
 * 反序列化头部
 */
int rpc_deserialize_header(const uint8_t *buffer, size_t buffer_size, rpc_header_t *header)
{
    if (buffer_size < sizeof(rpc_header_t) || header == NULL) {
        return -1;
    }

    memcpy(header, buffer, sizeof(rpc_header_t));

    /* 验证魔数 */
    if (header->magic != RPC_MAGIC_NUMBER) {
        return -1;
    }

    /* 验证版本 */
    if (header->version != RPC_VERSION) {
        return -1;
    }

    return 0;
}

/*
 * 反序列化登录响应
 */
int rpc_deserialize_login_resp(const uint8_t *buffer, size_t buffer_size, rpc_login_resp_t *resp)
{
    if (buffer_size < sizeof(rpc_login_resp_t) || resp == NULL) {
        return -1;
    }

    memcpy(resp, buffer, sizeof(rpc_login_resp_t));
    return 0;
}

/*
 * 反序列化响应
 */
int rpc_deserialize_response(const uint8_t *buffer, size_t buffer_size, rpc_response_t *resp)
{
    if (buffer_size < sizeof(rpc_response_t) || resp == NULL) {
        return -1;
    }

    memcpy(resp, buffer, sizeof(rpc_response_t));
    return 0;
}

/*
 * 网络字节序转换：主机到网络
 */
void rpc_hton_header(rpc_header_t *header)
{
    header->msg_type = htons(header->msg_type);
    header->msg_id = htonl(header->msg_id);
    header->payload_len = htonl(header->payload_len);
}

/*
 * 网络字节序转换：网络到主机
 */
void rpc_ntoh_header(rpc_header_t *header)
{
    header->msg_type = ntohs(header->msg_type);
    header->msg_id = ntohl(header->msg_id);
    header->payload_len = ntohl(header->payload_len);
}

/*
 * 消息类型字符串
 */
const char* rpc_msg_type_str(uint16_t msg_type)
{
    switch (msg_type) {
        case RPC_MSG_LOGIN:      return "LOGIN";
        case RPC_MSG_DATA:       return "DATA";
        case RPC_MSG_RESPONSE:   return "RESPONSE";
        case RPC_MSG_HEARTBEAT:  return "HEARTBEAT";
        case RPC_MSG_LOGOUT:     return "LOGOUT";
        default:                 return "UNKNOWN";
    }
}

/*
 * 错误码字符串
 */
const char* rpc_error_str(uint16_t error_code)
{
    switch (error_code) {
        case RPC_ERR_SUCCESS:         return "SUCCESS";
        case RPC_ERR_INVALID_MSG:     return "INVALID_MSG";
        case RPC_ERR_AUTH_FAILED:     return "AUTH_FAILED";
        case RPC_ERR_TIMEOUT:         return "TIMEOUT";
        case RPC_ERR_UNKNOWN_TYPE:    return "UNKNOWN_TYPE";
        case RPC_ERR_BUFFER_TOO_SMALL:return "BUFFER_TOO_SMALL";
        default:                      return "UNKNOWN";
    }
}

/*
 * 简单校验和
 */
uint32_t rpc_calc_checksum(const uint8_t *data, size_t len)
{
    uint32_t sum = 0;
    for (size_t i = 0; i < len; i++) {
        sum += data[i];
    }
    return sum;
}
