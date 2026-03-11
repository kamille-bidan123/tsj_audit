"""测试 Shell Session 功能"""

from tools.executor import ToolExecutor
from tools.shell_tool import ShellTool


def test_session_workflow():
    """测试完整的 session 工作流"""
    print("=" * 60)
    print("Shell Session 功能测试")
    print("=" * 60)

    # 1. 列出当前 session（应该是空的）
    print("\n1. 列出当前 session:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    # 2. 创建 session
    print("\n2. 创建 session 'test1':")
    result = ToolExecutor.call("create_session test1")
    print(result)

    # 3. 创建另一个 session
    print("\n3. 创建 session 'test2':")
    result = ToolExecutor.call("create_session test2")
    print(result)

    # 4. 列出 session
    print("\n4. 列出所有 session:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    # 5. 在 session1 中执行命令（切换目录）
    print("\n5. 在 test1 中执行 'cd /tmp':")
    result = ToolExecutor.call("session_exec test1 cd /tmp")
    print(result)

    # 6. 在 session1 中执行 pwd
    print("\n6. 在 test1 中执行 'pwd':")
    result = ToolExecutor.call("session_exec test1 pwd")
    print(result)

    # 7. 在 session2 中执行命令（保持在原目录）
    print("\n7. 在 test2 中执行 'pwd':")
    result = ToolExecutor.call("session_exec test2 pwd")
    print(result)

    # 8. 列出 session（显示不同 cwd）
    print("\n8. 列出所有 session（注意 cwd 不同）:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    # 9. 在 session1 中执行 ls
    print("\n9. 在 test1 中执行 'ls -la /tmp | head -5':")
    result = ToolExecutor.call("session_exec test1 'ls -la /tmp | head -5'")
    print(result)

    # 10. 关闭 session1
    print("\n10. 关闭 test1:")
    result = ToolExecutor.call("close_session test1")
    print(result)

    # 11. 再次列出 session
    print("\n11. 列出所有 session（test1 已关闭）:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    # 12. 清理：关闭 test2
    print("\n12. 关闭 test2:")
    result = ToolExecutor.call("close_session test2")
    print(result)

    # 13. 最终列出 session
    print("\n13. 最终列出 session:")
    result = ToolExecutor.call("list_sessions")
    print(result)

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    test_session_workflow()
