/**
 * 工具函数实现
 */
#include "utils.h"
#include <stdarg.h>
#include <time.h>
#include <errno.h>

void generate_random_string(char* buf, size_t size, size_t len) {
    const char chars[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    if (len >= size) len = size - 1;
    for (size_t i = 0; i < len; i++) {
        buf[i] = chars[rand() % (sizeof(chars) - 1)];
    }
    buf[len] = '\0';
}

char* trim(char* str) {
    if (!str) return str;

    // 去除开头空白
    while (*str == ' ' || *str == '\t' || *str == '\n' || *str == '\r') {
        str++;
    }

    if (*str == '\0') return str;

    // 去除结尾空白
    char* end = str + strlen(str) - 1;
    while (end > str && (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r')) {
        *end-- = '\0';
    }

    return str;
}

const char* json_get_string(const char* json, const char* key, char* buf, size_t size) {
    if (!json || !key || !buf || size == 0) return NULL;

    char search_key[256];
    snprintf(search_key, sizeof(search_key), "\"%s\"", key);

    const char* key_pos = strstr(json, search_key);
    if (!key_pos) return NULL;

    const char* colon = strchr(key_pos, ':');
    if (!colon) return NULL;

    // 跳过空白
    while (*colon == ' ' || *colon == '\t') colon++;

    if (*colon != '"') return NULL;

    colon++;
    const char* end = strchr(colon, '"');
    if (!end) return NULL;

    size_t len = end - colon;
    if (len >= size) len = size - 1;

    strncpy(buf, colon, len);
    buf[len] = '\0';

    return buf;
}

void sha256_hash(const char* input, char* output) {
    // 简化版本：使用简单的哈希算法模拟SHA256
    unsigned long hash = 5381;
    int c;
    const unsigned char* str = (const unsigned char*)input;

    while ((c = *str++)) {
        hash = ((hash << 5) + hash) + c;
    }

    snprintf(output, 65, "%016lx", hash);
    // 注意：这只是一个简单的哈希模拟，实际应用中应使用真正的SHA256实现
}

void log_info(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "[INFO] ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
}

void log_error(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "[ERROR] ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
}

void log_debug(const char* fmt, ...) {
#ifdef DEBUG
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "[DEBUG] ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
#endif
}

int get_timestamp(char* buf, size_t size) {
    time_t now = time(NULL);
    struct tm* tm_info = localtime(&now);
    return strftime(buf, size, "%Y-%m-%d %H:%M:%S", tm_info);
}

void safe_strcpy(char* dest, const char* src, size_t dest_size) {
    if (dest_size == 0) return;
    strncpy(dest, src, dest_size - 1);
    dest[dest_size - 1] = '\0';
}
