from pathlib import Path


FORBIDDEN_IMPORTS = ("nonebot", "openai", "aiosqlite", "httpx")


def test_core_does_not_depend_on_platform_or_provider_sdk() -> None:
    package_root = Path(__file__).parents[1] / "src" / "whale_girl"

    for folder in ("domain", "application", "ports"):
        for source_path in (package_root / folder).glob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_IMPORTS:
                assert f"import {forbidden}" not in source, (
                    f"{source_path} must not import {forbidden}"
                )
                assert f"from {forbidden}" not in source, (
                    f"{source_path} must not import {forbidden}"
                )
