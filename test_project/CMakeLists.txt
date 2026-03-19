cmake_minimum_required(VERSION 3.14)
project(notes_app C)

# 设置 CMake 策略
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# 查找 SQLite3（macOS 系统自带）
# macOS SDK 在 /Library/Developer/CommandLineTools/SDKs/ 目录下
find_path(SQLITE3_INCLUDE_DIR sqlite3.h
    PATHS
        /Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk/usr/include
        /Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk/usr/include
        /usr/local/include
        /opt/homebrew/include
        /usr/include
    NO_DEFAULT_PATH
)

find_library(SQLITE3_LIBRARY NAMES sqlite3 sqlite
    PATHS
        /Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk/usr/lib
        /Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk/usr/lib
        /usr/local/lib
        /opt/homebrew/lib
        /usr/lib
    NO_DEFAULT_PATH
)

if(SQLITE3_INCLUDE_DIR AND SQLITE3_LIBRARY)
    message(STATUS "Found SQLite3 include dir: ${SQLITE3_INCLUDE_DIR}")
    message(STATUS "Found SQLite3 library: ${SQLITE3_LIBRARY}")
else()
    # 尝试使用 pkg-config（Linux）
    find_package(PkgConfig QUIET)
    if(PKG_CONFIG_FOUND)
        pkg_check_modules(SQLITE3 QUIET sqlite3)
        set(SQLITE3_INCLUDE_DIR ${SQLITE3_INCLUDE_DIRS})
        set(SQLITE3_LIBRARY ${SQLITE3_LIBRARIES})
    endif()
endif()

if(NOT SQLITE3_INCLUDE_DIR OR NOT SQLITE3_LIBRARY)
    message(FATAL_ERROR "SQLite3 not found. Please install SQLite3 or ensure Xcode Command Line Tools are installed.")
endif()

# 使用 FetchContent 拉取 CivetWeb 依赖
include(FetchContent)

FetchContent_Declare(
    civetweb
    GIT_REPOSITORY https://github.com/civetweb/civetweb.git
    GIT_TAG v1.16
)

# 设置 CivetWeb 构建选项
set(WORKERS 10 CACHE STRING "Number of worker threads")
set(USE_CXX OFF CACHE BOOL "Do not build C++ support")
set(USE_TEST OFF CACHE BOOL "Do not build tests")
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static library")
set(ENABLE_CGI OFF CACHE BOOL "Disable CGI")
set(CIVETWEB_BUILD_TESTING OFF CACHE BOOL "Disable CivetWeb tests")

FetchContent_MakeAvailable(civetweb)

# 获取 civetweb 的 include 目录
FetchContent_GetProperties(civetweb)
set(CIVETWEB_INCLUDE_DIR "${civetweb_SOURCE_DIR}/include")

# ==================== 源文件定义 ====================
set(SRC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/src)

# Web 进程源文件
set(WEB_SOURCES
    ${SRC_DIR}/main_web.c
    ${SRC_DIR}/db.c
    ${SRC_DIR}/utils.c
    ${SRC_DIR}/note_logic.c
    ${SRC_DIR}/rpc.c
)

# Worker 进程源文件
set(WORKER_SOURCES
    ${SRC_DIR}/main_worker.c
    ${SRC_DIR}/db.c
    ${SRC_DIR}/utils.c
    ${SRC_DIR}/rpc.c
)

# ==================== Web 服务进程 ====================
add_executable(notes_web ${WEB_SOURCES})

target_include_directories(notes_web PRIVATE
    ${SRC_DIR}
    ${CIVETWEB_INCLUDE_DIR}
    ${SQLITE3_INCLUDE_DIR}
)

target_link_libraries(notes_web PRIVATE
    ${SQLITE3_LIBRARY}
    pthread
)

# 链接 CivetWeb 库
if(TARGET civetweb_lib)
    target_link_libraries(notes_web PRIVATE civetweb_lib)
elseif(TARGET civetweb-c-library)
    target_link_libraries(notes_web PRIVATE civetweb-c-library)
elseif(TARGET civetweb)
    target_link_libraries(notes_web PRIVATE civetweb)
endif()

target_compile_options(notes_web PRIVATE -Wall -Wextra -g)

# ==================== Worker 进程 ====================
add_executable(notes_worker ${WORKER_SOURCES})

target_include_directories(notes_worker PRIVATE
    ${SRC_DIR}
    ${CIVETWEB_INCLUDE_DIR}
    ${SQLITE3_INCLUDE_DIR}
)

target_link_libraries(notes_worker PRIVATE
    ${SQLITE3_LIBRARY}
    pthread
)

# 链接 CivetWeb 库（用于 RPC）
if(TARGET civetweb_lib)
    target_link_libraries(notes_worker PRIVATE civetweb_lib)
elseif(TARGET civetweb-c-library)
    target_link_libraries(notes_worker PRIVATE civetweb-c-library)
elseif(TARGET civetweb)
    target_link_libraries(notes_worker PRIVATE civetweb)
endif()

target_compile_options(notes_worker PRIVATE -Wall -Wextra -g)

# ==================== 安装 ====================
install(TARGETS notes_web notes_worker DESTINATION bin)

# ==================== 打包 ====================
message(STATUS "CivetWeb include dir: ${CIVETWEB_INCLUDE_DIR}")
message(STATUS "SQLite3 include dir: ${SQLITE3_INCLUDE_DIR}")
message(STATUS "SQLite3 library: ${SQLITE3_LIBRARY}")
