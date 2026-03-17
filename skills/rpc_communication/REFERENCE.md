---
name: rpc-protocol
description: RPC 协议格式定义
---

# RPC 协议格式定义

## 二进制协议结构

### 消息头格式 (固定 16 字节)

```
Offset  Size  Field           Description
------  ----  -----           -----------
0       4     Magic Number    魔数 0x52504300 ('RPC\0')
4       1     Version         协议版本 (默认 1)
5       1     Flags           标志位 (0x01 = request, 0x02 = response)
6       2     Message Type    消息类型 (0x0001 = login, 0x0002 = data, 0x0003 = response)
8       4     Message ID      消息 ID (事务 ID)
12      4     Payload Length  负载长度 (不包含头部)
```

### 消息体格式 (可变长度)

```
Offset  Size  Field           Description
------  ----  -----           -----------
0       4     Source ID       源地址 ID
4       4     Target ID       目标地址 ID
8       2     Port            端口号
10      2     Command         命令码
12      N     Data            实际数据
```

### 消息类型

| 值 | 名称 | 描述 |
|----|------|------|
| 0x0001 | RPC_MSG_LOGIN | 登录请求 |
| 0x0002 | RPC_MSG_DATA | 数据传输 |
| 0x0003 | RPC_MSG_RESPONSE | 响应消息 |
| 0x0004 | RPC_MSG_HEARTBEAT | 心跳包 |

### 错误码

| 值 | 名称 | 描述 |
|----|------|------|
| 0 | RPC_ERR_SUCCESS | 成功 |
| 1 | RPC_ERR_INVALID_MSG | 无效消息 |
| 2 | RPC_ERR_AUTH_FAILED | 认证失败 |
| 3 | RPC_ERR_TIMEOUT | 超时 |
| 4 | RPC_ERR_UNKNOWN_TYPE | 未知消息类型 |
