---
name: rpc-communication
description: 分析和跟踪 RPC 通信机制中的数据流，包括序列化、网络传输、反序列化过程
version: 1.0
author: Security Team
tags:
  - network
  - rpc
  - data-flow
---

# RPC 通信机制分析

当需要分析 RPC（Remote Procedure Call）通信中的数据流时使用此 Skill。

## RPC 数据流跟踪

### 1. 数据流阶段

RPC 通信通常包含以下阶段：

```
发送端 (Client)                  接收端 (Server)
   |                              |
   | 1. 应用数据                  |
   | 2. 序列化 (Serialize)        |
   | 3. 构建 RPC Header           |
   | 4. 发送网络包                |
   |------------------------------->|
   |                              | 5. 接收网络包
   |                              | 6. 解析 RPC Header
   |                              | 7. 反序列化 (Deserialize)
   |                              | 8. 处理业务逻辑
   |                              | 9. 构建响应
   |                              | 10. 序列化响应
   |                              | 11. 发送响应
   |<-------------------------------|
   | 12. 接收响应                 |
   | 13. 解析响应                  |
   | 14. 反序列化响应              |
   | 15. 返回调用结果              |
```

### 2. 关键跟踪点

#### 序列化函数
- 查找序列化/反序列化函数调用
- 识别数据字段映射关系
- 追踪数据结构布局

#### 网络通信函数
- 关注 socket send/recv 相关函数
- 查找网络字节序转换函数 (htonl, htons, ntohl, ntohs)
- 跟踪 buffer 传递

#### 协议解析
- 查找协议头解析逻辑
- 识别消息类型字段
- 追踪消息 ID/事务 ID

### 3. 常见 RPC 协议特征

#### 自定义二进制协议
- 固定长度头部（魔数、版本、消息类型、消息长度）
- 可变长度负载
- 校验和字段

#### HTTP/JSON RPC
- HTTP 请求/响应
- JSON 格式 payload
- 标准化格式

### 4. 数据流分析建议

1. **从网络接收点开始**：
   - 定位 socket recv / read 等函数
   - 追踪接收到的 buffer

2. **查找解析逻辑**：
   - 检查消息头解析
   - 根据消息类型分发到不同处理函数

3. **追踪业务处理**：
   - 查找消息体解析
   - 追踪参数传递路径

4. **反向跟踪**：
   - 从响应发送点反向查找
   - 确定响应数据来源

## 示例项目结构

```
test_project/rpc_demo/
├── rpc.h                 # RPC 协议定义
├── rpc_client.c          # RPC 客户端（发送端）
├── rpc_server.c          # RPC 服务器（接收端）
└── handler.c             # 业务处理函数
```

## 相关资源

- [REFERENCE.md](REFERENCE.md) - 详细的协议格式说明
- [scripts/](scripts/) - RPC 分析工具脚本
