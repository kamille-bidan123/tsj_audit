"""测试 Tool Call 架构"""

from agents.code_audit_agent import CodeAuditAgent, SimpleAgent
from tools.prompt_generator import ToolPromptGenerator
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


def test_tool_registry():
    """测试工具注册"""
    print("=" * 50)
    print("测试工具注册")
    print("=" * 50)
    print(f"已注册命令：{ToolRegistry.get_all_commands()}")
    print()


def test_prompt_generation():
    """测试 Prompt 生成"""
    print("=" * 50)
    print("测试 Prompt 生成")
    print("=" * 50)

    # 生成全部工具的 prompt
    print("全部工具:")
    print(ToolPromptGenerator.generate())
    print()


def test_agent_prompt():
    """测试 Agent 的 system prompt"""
    print("=" * 50)
    print("测试 Agent System Prompt")
    print("=" * 50)

    agent = CodeAuditAgent()
    print(f"Agent: {agent.name}")
    print(f"工具列表：{agent.tools}")
    print()
    print("System Prompt:")
    print(agent.get_system_prompt())
    print()


def test_tool_execution():
    """测试工具执行"""
    print("=" * 50)
    print("测试工具执行")
    print("=" * 50)

    # 测试 list_dir
    print("测试 list_dir:")
    result = ToolExecutor.call("list_dir .")
    print(result)
    print()

    # 测试 read_file (读取自己的 main.py)
    print("测试 read_file main.py:1-10:")
    result = ToolExecutor.call("read_file main.py:1-10")
    print(result)
    print()

    # 测试 search_code
    print("测试 search_code def main:")
    result = ToolExecutor.call("search_code \"def main\" .")
    print(result)
    print()


def test_agent_execution():
    """测试 Agent 执行工具"""
    print("=" * 50)
    print("测试 Agent 执行")
    print("=" * 50)

    agent = CodeAuditAgent()

    # 模拟 LLM 返回
    response = {
        "command": "read_file main.py:1-10",
        "logic": "查看 main.py 的前 10 行代码",
    }
    print(f"LLM 返回：{response}")
    result = agent.handle_llm_response(response)
    print(f"执行结果：{result}")
    print()

    # 测试 SimpleAgent 的权限限制
    print("测试 SimpleAgent 权限限制:")
    simple_agent = SimpleAgent()
    response = {
        "command": "search_code test .",
        "logic": "搜索 test",
    }
    print(f"LLM 返回：{response}")
    result = simple_agent.handle_llm_response(response)
    print(f"执行结果：{result}")
    print()


def main():
    test_tool_registry()
    test_tool_execution()
    test_agent_prompt()
    test_agent_execution()
    print("所有测试完成!")


if __name__ == "__main__":
    main()
