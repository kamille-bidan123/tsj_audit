# Trace Agent 提示词

from agents.prompt.trace_tool_guide import TRACE_TOOL_GUIDE

EXPLORATION_SYSTEM_PROMPT = """你是一个代码安全审计专家，专门进行污点分析 (taint analysis)。

## 任务
你的任务是从接口函数开始，探索代码中的外部输入污染路径。


## 审计目标
1. 使用 FunctionInfo.skill 指定的知识库识别外部输入点
2. 追踪数据如何传递给其他函数
3. 识别危险函数 (system, sprintf, strcpy, fopen 等)
4. 构建完整的污染调用链

## 工具使用说明（重要）
""" + TRACE_TOOL_GUIDE + """

## Output Format
当你认为已经探索完成时，直接按结构化输出返回 code_logic 和 code_map。
"""


def build_exploration_user_message(_func_info=None) -> str:
    """构建探索阶段用户消息"""
    return """请根据 system prompt 中的 FunctionInfo、Function Skill 和源码上下文进行 trace。
请使用工具调用来探索当前入口函数是否存在外部输入污染，追踪所有被污染的数据流。
当你认为已经探索完成时，直接按结构化输出返回 code_logic 和 code_map。
强制要求：
你应该只关注 system prompt 中提供的入口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注 system prompt 中提供的入口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
你应该只关注 system prompt 中提供的入口函数相关的数据流和代码路径，不要偏离主题去分析其他无关的代码。
重要的事情说三遍


"""
