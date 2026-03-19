/**
 * 工具函数模块
 */
#ifndef UTILS_H
#define UTILS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// 生成随机字符串
void generate_random_string(char* buf, size_t size, size_t len);

// 去除字符串首尾空白
char* trim(char* str);

// 从字符串中提取JSON字段
const char* json_get_string(const char* json, const char* key, char* buf, size_t size);

// 将字符串转换为SHA256哈希（简化版，实际应使用crypto库）
void sha256_hash(const char* input, char* output);

// 日志函数
void log_info(const char* fmt, ...);
void log_error(const char* fmt, ...);
void log_debug(const char* fmt, ...);

// 时间戳
int get_timestamp(char* buf, size_t size);

// 安全地复制字符串
void safe_strcpy(char* dest, const char* src, size_t dest_size);

#endif /* UTILS_H */
