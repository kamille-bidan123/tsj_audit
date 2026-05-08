#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Password reset audit agent backed by DeepAgents."""

import json
from typing import List

from agents.deepagents_audit_runner import DeepAgentsAuditRunner
from models import AuditResult, CodeContext, FunctionInfo


class PasswordResetAgent:
    """Web 重置密码漏洞审计 Agent。"""

    RESET_KEYWORDS = [
        "reset_password", "change_password", "update_password",
        "modify_password", "set_password", "new_password",
        "password_reset", "password_change", "password_update",
    ]

    OLD_PASSWORD_KEYWORDS = [
        "old_password", "old_passwd", "old_pwd", "current_password",
        "current_passwd", "current_pwd", "previous_password",
        "verify_old", "check_old", "auth_old",
    ]

    TOKEN_KEYWORDS = [
        "token", "verify_token", "reset_token", "password_token",
        "code", "verify_code", "reset_code", "otp", "verification_code",
        "sms_code", "email_token",
    ]

    SECURITY_KEYWORDS = [
        "security_question", "security_q", "secret_question",
        "verify_question", "answer",
    ]

    def __init__(
        self,
        function_info: FunctionInfo,
        code_map: List[CodeContext],
        project_path: str = ".",
        debug: bool = False,
        output_dir: str = None,
    ):
        self.function_info = function_info
        self.code_map = code_map
        self.project_path = project_path
        self.debug = debug
        self.output_dir = output_dir

    def audit(self) -> AuditResult:
        return DeepAgentsAuditRunner(
            agent_name="password_reset_agent",
            vulnerability_type="password_reset",
            function_info=self.function_info,
            code_map=self.code_map,
            system_prompt=self._build_system_prompt(),
            user_message=self._build_user_message(),
            project_path=self.project_path,
            debug=self.debug,
            output_dir=self.output_dir,
        ).run()

    def _build_system_prompt(self) -> str:
        return f"""你是一个代码安全审计专家，专门进行 Web 重置密码漏洞审计。

## 任务
从接口函数 {self.function_info.func_name} 开始，基于提供的 codemap，分析代码中是否存在密码重置漏洞。

## 漏洞定义
密码重置漏洞指：攻击者可以在不需要提供旧密码，或不满足必要身份校验的情况下设置新密码。

## 审计要点
1. 检查密码重置函数中是否需要提供旧密码。
2. 识别密码重置的验证方式：旧密码、令牌/验证码、安全问题、邮箱/手机号等。
3. 分析数据流：外部输入 -> 密码重置 -> 身份校验/旧密码验证 -> 新密码设置。
4. 检查令牌是否过期、单次使用、绑定账号或绑定场景。

## 漏洞判断标准
- 无需任何验证即可重置密码 -> 高置信度严重漏洞。
- 仅提供邮箱/手机号即可重置密码 -> 高置信度严重漏洞。
- 无需旧密码且令牌/验证码可绕过或弱绑定 -> 高置信度或中置信度漏洞。
- 需要旧密码进行验证 -> 通常无漏洞。
- 需要令牌/验证码且有过期、单次使用、账号绑定等额外验证 -> 低风险或无漏洞。

## 分析约束
- 只关注接口函数 {self.function_info.func_name} 相关的数据流和代码路径。
- 不要通过全局搜索关键词代替数据流分析；grep 只用于定位 RPCID、路由 ID、动态分发标识等必要场景。
- 如果不能确认数据流与接口函数相关，不要把无关代码纳入结论。
"""

    def _build_user_message(self) -> str:
        code_map_str = json.dumps(
            [ctx.model_dump() for ctx in self.code_map],
            indent=2,
            ensure_ascii=False,
        )

        return f"""请基于以下 codemap 进行密码重置漏洞审计：

```json
{code_map_str}
```

请结合必要源码确认密码重置接口是否需要旧密码或等价安全校验，并返回结构化审计结果。"""
