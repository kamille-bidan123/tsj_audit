#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skills 工具

扫描并加载 Skills 目录中的技能，支持按名称触发和加载 Skill 文档。
基于文件系统的 Skills 架构，实现渐进式披露机制。
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from tools.registry import ToolRegistry


def _get_config():
    """获取全局配置"""
    try:
        from cli import get_config
        return get_config()
    except ImportError:
        return None


def _parse_yaml_frontmatter(content: str) -> Dict[str, str]:
    """
    解析 SKILL.md 文件的 YAML 前置信息

    支持两种格式：
    1. --- 包围的 YAML 块
    2. 直接的键值对（name: xxx, description: xxx）

    Args:
        content: 文件内容

    Returns:
        解析后的元数据字典
    """
    metadata = {}

    # 尝试匹配 --- 包围的 YAML 块
    yaml_pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(yaml_pattern, content, re.DOTALL)
    if match:
        yaml_block = match.group(1)
        # 解析 YAML 键值对
        for line in yaml_block.strip().split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()

    # 查找 name 字段（支持 YAML 格式或普通标题）
    # YAML 格式: name: xxx
    if 'name' not in metadata:
        name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
        if name_match:
            metadata['name'] = name_match.group(1).strip()

    # 查找 description 字段
    if 'description' not in metadata:
        desc_match = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
        if desc_match:
            metadata['description'] = desc_match.group(1).strip()

    return metadata


def _get_skills_path() -> Path:
    """获取 Skills 目录路径"""
    config = _get_config()
    if config:
        skills_path = getattr(config, 'skills_path', None)
        if skills_path:
            return Path(skills_path)

    # 默认路径
    return Path.cwd() / "skills"


@ToolRegistry.register
class SkillsTool:
    """Skills 管理工具

    扫描 skills/ 目录，加载所有 Skill 的元数据。
    支持按名称触发和加载 Skill 文档。
    """

    name = "skill"
    description = "Skills 管理和触发"

    # 类级别的 Skills 缓存
    _skills: Dict[str, dict] = {}
    _skills_loaded = False

    # 命令定义
    commands = {
        "skill": {
            "description": "触发并加载指定名称的 Skill 文档。使用 name 参数选择要加载的 Skill，例如：{\"name\": \"rpc-communication\"}",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "要加载的 Skill 名称（例如：rpc-communication）。该名称必须与扫描到的 Skills 列表中的名称匹配。",
                    },
                },
                "required": ["name"],
            },
        },
    }

    def __init__(self):
        """初始化时自动扫描和加载 Skills"""
        if not self.__class__._skills_loaded:
            self.__class__._skills_loaded = True
            self._load_all_skills()

        # 更新 commands 描述为动态生成的描述
        if 'skill' in self.commands:
            self.commands['skill']['description'] = self._build_command_description()

    @classmethod
    def _load_all_skills(cls):
        """扫描并加载所有 Skills"""
        skills_path = _get_skills_path()
        cls._skills = {}

        if not skills_path.exists():
            if _get_config() and getattr(_get_config(), 'debug', False):
                print(f"[DEBUG] Skills 目录不存在: {skills_path}", file=__import__('sys').stderr)
            return

        # 遍历 Skills 目录
        for skill_dir in skills_path.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                continue

            try:
                content = skill_md_path.read_text(encoding='utf-8')
                metadata = _parse_yaml_frontmatter(content)

                # 获取技能名称（从 YAML 或目录名）
                skill_name = metadata.get('name', skill_dir.name)

                # 获取描述
                description = metadata.get('description', '无描述')

                cls._skills[skill_name] = {
                    'name': skill_name,
                    'path': str(skill_dir),
                    'skill_md_path': str(skill_md_path),
                    'description': description,
                    'content': content,
                }
            except Exception as e:
                if _get_config() and getattr(_get_config(), 'debug', False):
                    print(f"[DEBUG] 加载 Skill 失败 {skill_dir.name}: {e}", file=__import__('sys').stderr)
                continue

    @classmethod
    def check_availability(cls) -> str:
        """检查 Skills 工具的可用性"""
        if not cls._skills_loaded:
            cls._load_all_skills()

        skill_count = len(cls._skills)
        if skill_count > 0:
            return f"可用（已加载 {skill_count} 个 Skills）"
        else:
            skills_path = _get_skills_path()
            return f"可用（Skills 目录: {skills_path}，待加载）"

    @classmethod
    def get_available_skills(cls) -> List[Dict]:
        """获取所有可用的 Skills 列表"""
        if not cls._skills_loaded:
            cls._load_all_skills()
        return list(cls._skills.values())

    def _build_command_description(self) -> str:
        """构建带有所有 Skills 信息的命令描述"""
        if not self.__class__._skills_loaded:
            self.__class__._load_all_skills()

        base_desc = "触发并加载指定名称的 Skill 文档"

        if not self.__class__._skills:
            return base_desc + "（当前无可用 Skills）"

        skills_info = []
        for skill_name, skill_info in self.__class__._skills.items():
            desc = skill_info.get('description', '无描述')
            # 限制描述长度
            if len(desc) > 100:
                desc = desc[:97] + "..."
            skills_info.append(f"  - {skill_name}: {desc}")

        return f"{base_desc}\n\n可用 Skills:\n" + "\n".join(skills_info)

    def execute(self, command: str, args: dict) -> str:
        """执行 Skill 命令

        Args:
            command: 命令名（始终为 "skill"）
            args: 参数字典，包含 name 字段

        Returns:
            Skill 的 SKILL.md 文档内容
        """
        skill_name = args.get("name", "")

        if not skill_name:
            return "错误：缺少 name 参数。请提供要触发的 Skill 名称。"

        # 确保已加载 Skills
        if not self.__class__._skills_loaded:
            self.__class__._load_all_skills()

        # 查找 Skill
        if skill_name not in self.__class__._skills:
            # 提供相似名称的建议
            suggestions = self._find_similar_skills(skill_name)
            if suggestions:
                return f"错误：未找到名为 '{skill_name}' 的 Skill。\n\n可用的 Skills:\n" + "\n".join(suggestions)
            return f"错误：未找到名为 '{skill_name}' 的 Skill。请使用 list_skills 命令查看可用的 Skills。"

        # 加载并返回 Skill 文档内容
        skill_info = self.__class__._skills[skill_name]
        skill_path = skill_info['skill_md_path']

        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        except Exception as e:
            return f"错误：无法读取 Skill 文档 '{skill_path}': {e}"

    def _find_similar_skills(self, name: str, max_suggestions: int = 5) -> List[str]:
        """查找名称相似的 Skills"""
        if not self.__class__._skills:
            return []

        suggestions = []
        name_lower = name.lower()

        for skill_name in self.__class__._skills.keys():
            # 简单的相似度匹配
            if name_lower in skill_name.lower() or skill_name.lower() in name_lower:
                suggestions.append(skill_name)

        return suggestions[:max_suggestions]


# 便捷函数，供其他模块使用

def load_all_skills():
    """加载所有 Skills（全局函数）"""
    SkillsTool._load_all_skills()


def get_skills() -> Dict[str, dict]:
    """获取已加载的 Skills（全局函数）"""
    if not SkillsTool._skills_loaded:
        SkillsTool._load_all_skills()
    return SkillsTool._skills


def get_skill(name: str) -> Optional[dict]:
    """获取指定名称的 Skill"""
    if not SkillsTool._skills_loaded:
        SkillsTool._load_all_skills()
    return SkillsTool._skills.get(name)
