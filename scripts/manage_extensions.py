#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local web UI for managing attack-surface skills and audit specs."""

from __future__ import annotations

import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_SPEC_DIR = PROJECT_ROOT / "audit_specs"
SKILLS_DIR = PROJECT_ROOT / "skills"
ATTACK_SURFACE_SKILLS_DIR = SKILLS_DIR / "attack_surface"
WEB_FILE = PROJECT_ROOT / "web" / "extensions_manager.html"
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ATTACK_SURFACE_SECTIONS = (
    "攻击面发现知识",
    "外部输入知识",
    "PoC 生成知识",
)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def validate_id(value: str, label: str = "id") -> str:
    value = (value or "").strip()
    if not value or not ID_RE.fullmatch(value):
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"{label} 只能包含字母、数字、下划线和短横线",
        )
    return value


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    try:
        data = json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"请求 JSON 无效: {exc}") from exc
    if not isinstance(data, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON object")
    return data


def yaml_dump(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"skill frontmatter 无法解析: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "skill frontmatter 必须是 mapping")
    return metadata, parts[2].lstrip("\n")


def render_skill(metadata: dict, body: str) -> str:
    body = (body or "").lstrip("\n")
    return f"---\n{yaml_dump(metadata)}\n---\n\n{body}"


def split_attack_surface_body(body: str) -> dict[str, str]:
    result = {key: "" for key in ATTACK_SURFACE_SECTIONS}
    current = None
    lines: list[str] = []
    for line in (body or "").splitlines():
        matched = None
        for section in ATTACK_SURFACE_SECTIONS:
            if line.strip() == f"## {section}":
                matched = section
                break
        if matched:
            if current:
                result[current] = "\n".join(lines).strip()
            current = matched
            lines = []
            continue
        if current:
            lines.append(line)
    if current:
        result[current] = "\n".join(lines).strip()
    return {
        "discovery_knowledge": result["攻击面发现知识"],
        "input_knowledge": result["外部输入知识"],
        "poc_knowledge": result["PoC 生成知识"],
    }


def render_attack_surface_body(data: dict) -> str:
    return (
        f"# {data.get('name') or 'Attack Surface Skill'}\n\n"
        "## 攻击面发现知识\n\n"
        f"{str(data.get('discovery_knowledge') or '').strip()}\n\n"
        "## 外部输入知识\n\n"
        f"{str(data.get('input_knowledge') or '').strip()}\n\n"
        "## PoC 生成知识\n\n"
        f"{str(data.get('poc_knowledge') or '').strip()}\n"
    )


def list_audit_specs() -> list[dict]:
    specs = []
    for path in sorted(AUDIT_SPEC_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        specs.append(
            {
                "id": path.stem,
                "name": data.get("name") or path.stem,
                "user_prompt": data.get("user_prompt") or "",
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    return specs


def save_audit_spec(spec_id: str, data: dict, *, create: bool) -> dict:
    spec_id = validate_id(spec_id, "audit spec id")
    name = validate_id(str(data.get("name") or spec_id), "audit type name")
    user_prompt = str(data.get("user_prompt") or "").strip()
    if not user_prompt:
        raise ApiError(HTTPStatus.BAD_REQUEST, "user_prompt 不能为空")

    path = AUDIT_SPEC_DIR / f"{spec_id}.yaml"
    if create and path.exists():
        raise ApiError(HTTPStatus.CONFLICT, f"audit spec 已存在: {spec_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml_dump({"name": name, "user_prompt": user_prompt}) + "\n",
        encoding="utf-8",
    )
    return {"id": spec_id, "name": name, "user_prompt": user_prompt, "path": path.relative_to(PROJECT_ROOT).as_posix()}


def delete_audit_spec(spec_id: str) -> dict:
    spec_id = validate_id(spec_id, "audit spec id")
    path = AUDIT_SPEC_DIR / f"{spec_id}.yaml"
    if not path.exists():
        raise ApiError(HTTPStatus.NOT_FOUND, f"audit spec 不存在: {spec_id}")
    path.unlink()
    return {"deleted": spec_id}


def list_skills() -> list[dict]:
    skills = []
    for skill_dir in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        if skill_dir.name == "attack_surface":
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        metadata, body = split_frontmatter(skill_file.read_text(encoding="utf-8"))
        skills.append(
            {
                "id": skill_dir.name,
                "name": metadata.get("name") or skill_dir.name,
                "description": metadata.get("description") or "",
                "metadata": metadata,
                "body": body,
                "path": skill_file.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    return skills


def list_attack_surface_skills() -> list[dict]:
    skills = []
    if not ATTACK_SURFACE_SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted(path for path in ATTACK_SURFACE_SKILLS_DIR.iterdir() if path.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        metadata, body = split_frontmatter(skill_file.read_text(encoding="utf-8"))
        sections = split_attack_surface_body(body)
        skills.append(
            {
                "id": skill_dir.name,
                "name": metadata.get("name") or skill_dir.name,
                "description": metadata.get("description") or "",
                "required_audit_types": metadata.get("required_audit_types") or [],
                "metadata": metadata,
                "body": body,
                **sections,
                "path": skill_file.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    return skills


def save_skill(skill_id: str, data: dict, *, create: bool) -> dict:
    skill_id = validate_id(skill_id, "skill id")
    name = str(data.get("name") or skill_id).strip()
    if not name:
        raise ApiError(HTTPStatus.BAD_REQUEST, "skill name 不能为空")
    description = str(data.get("description") or "").strip()
    body = str(data.get("body") or "").strip()
    if not body:
        raise ApiError(HTTPStatus.BAD_REQUEST, "SKILL.md 正文不能为空")

    skill_dir = SKILLS_DIR / skill_id
    skill_file = skill_dir / "SKILL.md"
    if create and skill_file.exists():
        raise ApiError(HTTPStatus.CONFLICT, f"skill 已存在: {skill_id}")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = {
        **metadata,
        "name": name,
        "description": description,
    }
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(render_skill(metadata, body), encoding="utf-8")
    return {
        "id": skill_id,
        "name": name,
        "description": description,
        "metadata": metadata,
        "body": body,
        "path": skill_file.relative_to(PROJECT_ROOT).as_posix(),
    }


def save_attack_surface_skill(skill_id: str, data: dict, *, create: bool) -> dict:
    skill_id = validate_id(skill_id, "attack surface skill id")
    name = str(data.get("name") or skill_id).strip()
    if not name:
        raise ApiError(HTTPStatus.BAD_REQUEST, "skill name 不能为空")
    description = str(data.get("description") or "").strip()
    required = data.get("required_audit_types") or []
    if isinstance(required, str):
        required = [item.strip() for item in required.split(",") if item.strip()]
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ApiError(HTTPStatus.BAD_REQUEST, "required_audit_types 必须是字符串数组")
    required = list(dict.fromkeys(validate_id(item, "audit type") for item in required if item.strip()))
    for field, label in (
        ("discovery_knowledge", "攻击面发现知识"),
        ("input_knowledge", "外部输入知识"),
        ("poc_knowledge", "PoC 生成知识"),
    ):
        if not str(data.get(field) or "").strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, f"{label} 不能为空")

    skill_dir = ATTACK_SURFACE_SKILLS_DIR / skill_id
    skill_file = skill_dir / "SKILL.md"
    if create and skill_file.exists():
        raise ApiError(HTTPStatus.CONFLICT, f"attack surface skill 已存在: {skill_id}")

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = {
        **metadata,
        "name": name,
        "description": description,
        "required_audit_types": required,
    }
    body = render_attack_surface_body({**data, "name": name})
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(render_skill(metadata, body), encoding="utf-8")
    sections = split_attack_surface_body(body)
    return {
        "id": skill_id,
        "name": name,
        "description": description,
        "required_audit_types": required,
        "metadata": metadata,
        "body": body,
        **sections,
        "path": skill_file.relative_to(PROJECT_ROOT).as_posix(),
    }


def delete_skill(skill_id: str, *, attack_surface: bool = False) -> dict:
    skill_id = validate_id(skill_id, "skill id")
    skill_dir = (ATTACK_SURFACE_SKILLS_DIR if attack_surface else SKILLS_DIR) / skill_id
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise ApiError(HTTPStatus.NOT_FOUND, f"skill 不存在: {skill_id}")
    extra_files = [path for path in skill_dir.rglob("*") if path.is_file() and path.name != "SKILL.md"]
    if extra_files:
        raise ApiError(
            HTTPStatus.CONFLICT,
            "该 skill 包含子文件，避免误删脚本/参考资料，请先手动处理子文件",
        )
    skill_file.unlink()
    skill_dir.rmdir()
    return {"deleted": skill_id}


class ExtensionManagerHandler(BaseHTTPRequestHandler):
    server_version = "TSJAuditExtensionManager/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[extension-ui] {self.address_string()} {fmt % args}", file=sys.stderr)

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def _handle(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path in {"/", "/index.html"}:
                self._send_file(WEB_FILE, "text/html; charset=utf-8")
                return
            if path == "/api/state" and self.command == "GET":
                self._send_json(
                    {
                        "audit_specs": list_audit_specs(),
                        "attack_surface_skills": list_attack_surface_skills(),
                        "skills": list_skills(),
                    }
                )
                return
            if path == "/api/audit-specs" and self.command == "GET":
                self._send_json({"items": list_audit_specs()})
                return
            if path == "/api/audit-specs" and self.command == "POST":
                body = read_json(self)
                spec_id = str(body.get("id") or body.get("name") or "")
                self._send_json(save_audit_spec(spec_id, body, create=True), HTTPStatus.CREATED)
                return
            if path.startswith("/api/audit-specs/"):
                spec_id = path.rsplit("/", 1)[-1]
                if self.command == "PUT":
                    self._send_json(save_audit_spec(spec_id, read_json(self), create=False))
                    return
                if self.command == "DELETE":
                    self._send_json(delete_audit_spec(spec_id))
                    return
            if path == "/api/attack-surface-skills" and self.command == "GET":
                self._send_json({"items": list_attack_surface_skills()})
                return
            if path == "/api/attack-surface-skills" and self.command == "POST":
                body = read_json(self)
                skill_id = str(body.get("id") or body.get("name") or "")
                self._send_json(save_attack_surface_skill(skill_id, body, create=True), HTTPStatus.CREATED)
                return
            if path.startswith("/api/attack-surface-skills/"):
                skill_id = path.rsplit("/", 1)[-1]
                if self.command == "PUT":
                    self._send_json(save_attack_surface_skill(skill_id, read_json(self), create=False))
                    return
                if self.command == "DELETE":
                    self._send_json(delete_skill(skill_id, attack_surface=True))
                    return
            if path == "/api/skills" and self.command == "GET":
                self._send_json({"items": list_skills()})
                return
            if path == "/api/skills" and self.command == "POST":
                body = read_json(self)
                skill_id = str(body.get("id") or body.get("name") or "")
                self._send_json(save_skill(skill_id, body, create=True), HTTPStatus.CREATED)
                return
            if path.startswith("/api/skills/"):
                skill_id = path.rsplit("/", 1)[-1]
                if self.command == "PUT":
                    self._send_json(save_skill(skill_id, read_json(self), create=False))
                    return
                if self.command == "DELETE":
                    self._send_json(delete_skill(skill_id))
                    return
            raise ApiError(HTTPStatus.NOT_FOUND, f"未知路径: {path}")
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # pragma: no cover - defensive API boundary.
            self._send_json({"error": f"服务端错误: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            raise ApiError(HTTPStatus.NOT_FOUND, f"文件不存在: {path}")
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="TSJ Audit extension manager UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ExtensionManagerHandler)
    print(f"[extension-ui] http://{args.host}:{args.port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[extension-ui] stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
