cmake_minimum_required(VERSION 3.14)
project(civetweb_test_project C)

# 设置 CMake 策略以兼容旧版本
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

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

# 主程序可执行文件
add_executable(server main.c)

# 添加 include 目录
target_include_directories(server PRIVATE ${CIVETWEB_INCLUDE_DIR})

# 链接 CivetWeb 库 (使用 civetweb-c-library 作为目标名)
if(TARGET civetweb_lib)
    target_link_libraries(server PRIVATE civetweb_lib)
elseif(TARGET civetweb-c-library)
    target_link_libraries(server PRIVATE civetweb-c-library)
elseif(TARGET civetweb)
    target_link_libraries(server PRIVATE civetweb)
else()
    # 如果没有找到目标，直接添加源文件
    target_compile_definitions(server PRIVATE CIVETWEB_DIRECT_INCLUDE)
endif()

# 添加编译选项
target_compile_options(server PRIVATE -Wall -Wextra)

# 安装目标
install(TARGETS server DESTINATION bin)
