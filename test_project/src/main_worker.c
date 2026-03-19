/**
 * Worker 进程 - 业务逻辑处理
 * 通过RPC与Web进程通信，处理业务逻辑
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <errno.h>
#include "db.h"
#include "rpc.h"

#define BUFFER_SIZE 4096

// 处理单个RPC请求
static int handle_rpc_request(const unsigned char* request_data, size_t request_len,
                               unsigned char* response_data, size_t response_len) {
    if (request_len < sizeof(rpc_request_t)) {
        fprintf(stderr, "Invalid request length\n");
        return -1;
    }

    rpc_request_t* request = (rpc_request_t*)request_data;
    rpc_response_t* response = (rpc_response_t*)response_data;

    // 初始化响应
    memset(response, 0, sizeof(*response));
    response->request_id = request->request_id;

    // 检查操作码
    if (request->op >= RPC_LAST_OP) {
        response->status = -1;
        snprintf(response->message, sizeof(response->message), "Unknown operation: %u", request->op);
        return sizeof(rpc_response_t);
    }

    // 调用处理器
    if (g_handlers[request->op]) {
        int rc = g_handlers[request->op](request, response);
        if (rc != 0) {
            response->status = -1;
        }
        return sizeof(rpc_response_t);
    }

    response->status = -1;
    snprintf(response->message, sizeof(response->message), "No handler for operation: %u", request->op);
    return sizeof(rpc_response_t);
}

// 主循环
static void worker_loop(void) {
    fprintf(stderr, "[Worker] Starting worker process (PID: %d)\n", getpid());

    // 打开FIFO进行读写
    int fifo_fd = open(RPC_PIPE_PATH, O_RDWR);
    if (fifo_fd == -1) {
        fprintf(stderr, "[Worker] Failed to open FIFO: %s\n", strerror(errno));
        return;
    }

    fprintf(stderr, "[Worker] FIFO opened successfully\n");

    unsigned char request_buffer[BUFFER_SIZE];
    unsigned char response_buffer[BUFFER_SIZE];

    while (1) {
        // 读取请求
        ssize_t n = read(fifo_fd, request_buffer, sizeof(request_buffer) - 1);
        if (n == -1) {
            if (errno == EINTR) continue;
            fprintf(stderr, "[Worker] Read error: %s\n", strerror(errno));
            break;
        }

        if (n == 0) {
            usleep(10000);  // 10ms
            continue;
        }

        // 处理请求
        memset(response_buffer, 0, sizeof(response_buffer));
        size_t response_len = handle_rpc_request(request_buffer, n, response_buffer, sizeof(response_buffer));

        // 写回响应
        if (response_len > 0) {
            ssize_t written = write(fifo_fd, response_buffer, response_len);
            if (written == -1) {
                fprintf(stderr, "[Worker] Write error: %s\n", strerror(errno));
            }
        }
    }

    close(fifo_fd);
    fprintf(stderr, "[Worker] Worker process stopped\n");
}

int main(int argc, char* argv[]) {
    printf("Worker Process Starting...\n");
    printf("=========================\n\n");

    // 初始化数据库
    if (db_init() != 0) {
        fprintf(stderr, "Failed to initialize database\n");
        return 1;
    }

    // 初始化RPC处理器
    if (rpc_init() != 0) {
        fprintf(stderr, "Failed to initialize RPC\n");
        db_close();
        return 1;
    }

    printf("Worker process ready (PID: %d)\n", getpid());
    printf("Waiting for requests from web process...\n\n");

    // 运行主循环
    worker_loop();

    // 清理
    rpc_close();
    db_close();

    printf("Worker process exit.\n");
    return 0;
}
