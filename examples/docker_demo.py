"""演示 Docker 透明模式和 Shell Session"""

from tools.executor import ToolExecutor
from agents.code_audit_agent import CodeAuditAgent


def main():
    print("=" * 60)
    print("Docker 透明模式演示")
    print("=" * 60)

    # ========== 模式 1: 本地模式（默认）==========
    print("\n### 本地模式 ###\n")
    ToolExecutor.set_local_mode()

    result = ToolExecutor.call("list_dir .")
    print(f"list_dir . 结果:\n{result}\n")

    # ========== 模式 2: Docker 模式 ==========
    print("\n### Docker 模式 ###\n")
    print("假设容器 ID 为 'abc123'，工作目录 /app/code")
    print("（如果没有容器，以下调用会失败，仅演示 API）\n")

    ToolExecutor.set_docker_mode(
        container_id="abc123",
        workdir="/app/code",
    )

    # LLM 的命令完全一样，透明路由到容器
    print("LLM 发送：read_file src/main.c:1-20")
    result = ToolExecutor.call("read_file src/main.c:1-20")
    print(f"结果：{result}")

    print("\nLLM 发送：list_dir .")
    result = ToolExecutor.call("list_dir .")
    print(f"结果：{result}")


def shell_session_demo():
    """演示 Shell Session 的 Docker 模式"""
    print("\n" + "=" * 60)
    print("Shell Session Docker 模式演示")
    print("=" * 60)

    # 设置 Docker 模式
    ToolExecutor.set_docker_mode(
        container_id="my_container",
        workdir="/app",
    )

    # 创建 Docker 内的 session
    print("\n1. 创建 Docker session 'audit':")
    result = ToolExecutor.call("create_session audit")
    print(result)

    # 在 Docker session 中执行命令
    print("\n2. 在 session 中执行 'cd /app/src':")
    result = ToolExecutor.call("session_exec audit cd /app/src")
    print(result)

    print("\n3. 在 session 中执行 'python --version':")
    result = ToolExecutor.call("session_exec audit python --version")
    print(result)

    # 列出 session
    print("\n4. 列出所有 session:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    # 关闭 session
    print("\n5. 关闭 session:")
    result = ToolExecutor.call("close_session audit")
    print(result)


def agent_example():
    """Agent 中使用 Docker 模式"""
    print("\n### Agent 集成 ###\n")

    # 1. 设置 Docker 模式
    ToolExecutor.set_docker_mode(
        container_id="my_container",
        workdir="/app/target",
    )

    # 2. 创建 Agent
    agent = CodeAuditAgent()

    # 3. LLM 调用工具，完全无感
    response = {
        "command": "read_file vuln.c:1-50",
        "logic": "查看漏洞文件",
    }
    result = agent.handle_llm_response(response)
    print(f"最终结果：{result}")


if __name__ == "__main__":
    main()
    # shell_session_demo()  # 需要实际容器才能运行
    # agent_example()  # 需要实际容器才能运行
