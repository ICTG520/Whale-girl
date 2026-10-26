from __future__ import annotations

import tomllib
from pathlib import Path

from whale_girl.domain.persona import PersonaVersion


class PersonaConfigError(ValueError):
    """The local persona configuration is missing or invalid."""


def load_persona(path: Path) -> PersonaVersion:
    if not path.is_file():
        raise PersonaConfigError(f"找不到人设配置: {path}")

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise PersonaConfigError(f"无法解析人设配置: {path}") from exc

    try:
        version = int(data["version"])
        name = str(data["name"]).strip()
        system_prompt = str(data["system_prompt"]).strip()
        active = bool(data.get("active", True))
    except (KeyError, TypeError, ValueError) as exc:
        raise PersonaConfigError(f"人设配置字段不完整: {path}") from exc

    if version < 1:
        raise PersonaConfigError("人设版本必须大于等于 1")
    if not name:
        raise PersonaConfigError("人设名称不能为空")
    if not system_prompt:
        raise PersonaConfigError("人设 system_prompt 不能为空")
    if not active:
        raise PersonaConfigError("当前人设配置必须处于 active 状态")

    return PersonaVersion(
        version=version,
        name=name,
        system_prompt=system_prompt,
        active=active,
    )
