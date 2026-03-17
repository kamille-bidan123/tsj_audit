# RPC 示例项目

这个项目演示了 Web 服务器与业务处理进程之间的 RPC 通信机制。

## 项目结构

```
rpc_demo/
├── rpc.h              # RPC 协议定义（消息格式、类型、错误码）
├── rpc_common.c       # RPC 协议实现（序列化、反序列化、工具函数）
├── rpc_server.c       # RPC 服务器端（接收端，处理业务）
├── rpc_client.c       # RPC 客户端（发送端，Web 服务器使用）
├── handler.c          # 业务处理函数
└── Makefile
```

## 数据流跟踪点

### 1. Web 服务器接收请求
- `web_server_handle_request()` - 入口点

### 2. 构建 RPC 消息
- `rpc_client_send_data()` - 序列化数据包
- `rpc_serialize_header()` - 序列化消息头
- `rpc_serialize_data_packet()` - 序列化负载

### 3. 网络发送
- `send()` - 发送到 RPC 服务器

### 4. RPC 服务器接收
- `rpc_server_process()` - 主处理循环
- `read()` - 读取消息
- `rpc_deserialize_header()` - 反序列化头部
- `rpc_deserialize_header()` - 反序列化负载

### 5. 消息分发
- `g_msg_handlers[]` - 消息处理表
- `handle_data_msg()` - 数据消息处理

### 6. 业务处理
- `handle_data_packet()` - 实际业务逻辑

### 7. 响应返回
- `rpc_response_t` - 响应结构
- `write()` - 发送响应

## 编译和运行

```bash
cd test_project/rpc_demo
make
./rpc_client
```

## 错误码

| 值 | 名称 | 描述 |
|----|------|------|
| 0 | RPC_ERR_SUCCESS | 成功 |
| 1 | RPC_ERR_INVALID_MSG | 无效消息 |
| 2 | RPC_ERR_AUTH_FAILED | 认证失败 |
| 3 | RPC_ERR_TIMEOUT | 超时 |
| 4 | RPC_ERR_UNKNOWN_TYPE | 未知消息类型 |

## 消息类型

| 值 | 名称 | 描述 |
|----|------|------|
| 0x0001 | RPC_MSG_LOGIN | 登录请求 |
| 0x0002 | RPC_MSG_DATA | 数据传输 |
| 0x0003 | RPC_MSG_RESPONSE | 响应 |
| 0x0004 | RPC_MSG_HEARTBEAT | 心跳 |
| 0x0005 | RPC_MSG_LOGOUT | 登出 |
