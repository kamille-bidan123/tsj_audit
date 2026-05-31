---
name: ioctl_audit
description: Use when auditing Linux/Unix ioctl attack surfaces, including driver
  ioctl handler discovery, user-space input tracing, vulnerability audit, and safe
  local PoC or harness generation.
required_audit_types:
- command_injection
- path_traversal
- loop
---

# ioctl Audit Skill

本 skill 覆盖 ioctl 攻击面的完整审计流程：入口发现、外部输入识别、数据流分析和 PoC 生成。

## 攻击面发现知识

发现所有 Linux/Unix ioctl 入口函数。优先使用本 skill 子文件 `scripts/scan.py` 中的扫描策略；如果 runtime 无法直接运行脚本，则按下面的注册逻辑手动搜索源码。

### file_operations / proc_ops 注册

搜索结构体成员注册：

- `.unlocked_ioctl = callback`
- `.compat_ioctl = callback`
- `.ioctl = callback`
- `.proc_ioctl = callback`

识别规则：

1. 结构体成员右侧的函数指针通常是真实 ioctl handler。
2. callback 的真实函数定义是 `EntrySpec` 入口。
3. 找不到真实函数定义、行号或代码片段的候选不要输出。
4. 同一 callback 被多个结构体注册时，只输出一次真实函数定义。

### 函数命名兜底

如果注册结构体不完整，搜索名称包含以下片段的函数定义：

- `ioctl`
- `unlocked_ioctl`
- `compat_ioctl`
- `proc_ioctl`

只有函数签名看起来像 ioctl handler 时才输出，例如包含 `struct file *`、`unsigned int cmd`、`unsigned long arg`、`cmd` 或 `arg` 参数。

### EntrySpec 输出要求

每个入口必须输出：

- `func_name`
- `file_path`
- `start_line`（如果可以定位，强烈建议输出）
- `skill: "ioctl_audit"`

不要输出 `end_line`、`code_snippet` 或外部输入字段；Trace Agent 会让 runtime 根据源码补齐上下文。
不要输出 Markdown，不要输出解释文字，只返回包含 `functions` 字段的 JSON object。

## 外部输入知识

### ioctl 外部输入点说明

ioctl handler 中以下数据都应视为用户空间可控输入：

- `cmd`：用户态传入的 ioctl 命令码。
- `arg`：用户态传入的整数值或用户空间指针。
- 经 `(void __user *)arg`、`(struct xxx __user *)arg` 等转换后的指针。
- `copy_from_user`、`get_user`、`__get_user` 从用户空间读取出的结构体、字段、长度、偏移、索引、路径、命令或指针。
- `copy_struct_from_user`、`strncpy_from_user`、`memdup_user`、`memdup_user_nul`、`vmemdup_user` 读取出的数据。

写回用户态的接口也要审计信息泄露风险：

- `copy_to_user`
- `put_user`
- `__put_user`

`access_ok` 只能说明指针范围检查，不代表用户数据内容可信；不要把它当成完整校验。

常见污染路径：

- `arg` -> `copy_from_user` -> 结构体字段 -> 长度、数组索引、循环上界、偏移。
- `arg` -> 用户结构体中的二级指针 -> 再次 `copy_from_user` / `copy_to_user`。
- `cmd` -> `switch` / 表索引 / 函数指针表 -> 缺少范围或默认分支校验。
- 用户字符串 -> 路径拼接 -> `filp_open` / `kern_path` / `vfs_*` / `request_firmware`。
- 用户字符串 -> 命令拼接 -> `call_usermodehelper` 或项目封装命令执行。
- 用户长度 -> `kmalloc` / `copy_from_user` / `memcpy` / 循环边界。
- 用户缓冲区 -> `copy_to_user` -> 未初始化内核栈/堆数据泄露。

Trace 要求：

1. 从当前 `FunctionInfo` 入口函数开始，不要全局扫描危险函数后直接下结论。
2. 优先识别入口参数中的 `cmd`、`arg`，以及从 `arg` 拷贝出的本地变量、结构体字段和二级用户指针。
3. 沿 helper 函数、结构体字段、私有设备上下文、全局状态和 callback 继续追踪数据流。
4. 只有外部输入能从入口函数传播到敏感操作时，才构成有效审计路径。
5. 对内核代码特别关注错误处理：`copy_from_user` 返回值、长度截断、整数溢出、锁保护、引用计数和释放路径。
6. 不要把本 skill 文档当成 taint source；真正的 taint source 必须来自当前代码里的变量、参数或 API 调用。

## PoC 生成知识

PoC 必须安全、最小化、可复现，并且只验证当前 finding 描述的入口和数据流。默认生成本地用户态 harness；不要构造会破坏设备状态、刷写固件、擦除数据或触发高负载的载荷。

### 用户态 ioctl Harness

如果能推断设备节点和命令码，优先生成 C 或 Python harness：

```c
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void) {
    int fd = open("/dev/TARGET", O_RDWR);
    if (fd < 0) {
        perror("open");
        return 1;
    }

    struct {
        uint32_t len;
        char data[16];
    } arg = {
        .len = 16,
        .data = "TSJ_AUDIT_SAFE",
    };

    int ret = ioctl(fd, TARGET_CMD, &arg);
    printf("ret=%d\n", ret);
    close(fd);
    return 0;
}
```

### 命令码和设备节点未知时

如果缺少可执行上下文，生成最小 harness 模板并明确标注需要替换：

- 设备节点，例如 `/dev/TARGET`、`/proc/TARGET` 或项目注册出的节点。
- ioctl 命令码，例如 `_IOW(...)`、`_IOR(...)`、`_IOWR(...)` 或具体宏值。
- 用户结构体字段，只填充验证 finding 所需的最小字段。

### 约束

- 不要执行破坏性写入、删除、固件升级、权限持久化或高负载请求。
- 对命令注入只使用无害 echo 标记，例如 `TSJ_AUDIT_SAFE`。
- 对路径问题只访问最小安全目标，不修改系统文件。
- 对循环/DoS 问题优先使用小规模边界值，说明放大条件，不实际执行高负载。
- PoC 成功标准必须来自返回值、错误码、内核日志、无害 echo 标记、响应差异或可观察的安全失败路径。
