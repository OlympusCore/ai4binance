"""Small frontmatter parser for local Agent Skills.

This intentionally parses only the subset of YAML used by the Agent Skills
frontmatter contract.  It never executes bundled scripts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from ai4binance.skills.models import SkillManifest

MAX_SKILL_MD_BYTES = 256_000
_REFERENCE = re.compile(r"\]\(([^)]+)\)|(?:^|\s)(references/[^\s)]+)", re.MULTILINE)


class SkillParseError(ValueError):
    """Raised when a local skill cannot be parsed safely."""


def discover_skill_paths(root: Path) -> tuple[Path, ...]:
    resolved = root.resolve()
    if not resolved.exists():
        raise SkillParseError(f"skill root does not exist: {resolved}")
    if (resolved / "SKILL.md").is_file():
        return (resolved,)
    if not resolved.is_dir():
        raise SkillParseError(f"skill root is not a directory: {resolved}")
    return tuple(
        path
        for path in sorted(resolved.iterdir(), key=lambda item: item.name.casefold())
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def read_skill(skill_dir: Path) -> SkillManifest:
    resolved_dir = skill_dir.resolve()
    skill_file = resolved_dir / "SKILL.md"
    if not skill_file.is_file():
        raise SkillParseError(f"SKILL.md missing: {resolved_dir}")
    if skill_file.stat().st_size > MAX_SKILL_MD_BYTES:
        raise SkillParseError(f"SKILL.md exceeds {MAX_SKILL_MD_BYTES} bytes")
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, skill_file)
    fields = _parse_frontmatter(frontmatter, skill_file)
    metadata = _metadata_field(fields, skill_file)
    return SkillManifest(
        skill_dir=str(resolved_dir),
        skill_file=str(skill_file),
        name=_string_field(fields, "name", skill_file),
        description=_string_field(fields, "description", skill_file),
        license=_optional_string_field(fields, "license", skill_file),
        compatibility=_optional_string_field(fields, "compatibility", skill_file),
        metadata=metadata,
        allowed_tools=_optional_string_field(fields, "allowed-tools", skill_file),
        body=body,
        referenced_files=_extract_references(body),
        optional_directories=_optional_directories(resolved_dir),
        root_files=_root_files(resolved_dir),
        version=_metadata_value(metadata, "ai4binance.version"),
        owner=_metadata_value(metadata, "ai4binance.owner"),
        trust_level=_metadata_value(metadata, "ai4binance.trust_level"),
        last_reviewed=_metadata_value(metadata, "ai4binance.last_reviewed"),
        trigger_examples=_metadata_tuple(metadata, "ai4binance.trigger_examples"),
    )


def _split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillParseError(f"frontmatter opening delimiter missing: {path}")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body
    raise SkillParseError(f"frontmatter closing delimiter missing: {path}")


def _parse_frontmatter(frontmatter: str, path: Path) -> dict[str, object]:
    fields: dict[str, object] = {}
    current_map: str | None = None
    for raw_line in frontmatter.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")):
            if current_map != "metadata":
                raise SkillParseError(f"unsupported nested frontmatter: {path}")
            key, value = _parse_key_value(raw_line.strip(), path)
            metadata = fields.setdefault("metadata", {})
            if not isinstance(metadata, dict):
                raise SkillParseError(f"metadata must be a mapping: {path}")
            metadata[str(key)] = _strip_quotes(str(value))
            continue
        key, value = _parse_key_value(raw_line, path)
        current_map = None
        if key == "metadata" and value == "":
            fields["metadata"] = {}
            current_map = "metadata"
            continue
        fields[key] = _strip_quotes(value)
    return fields


def _string_field(fields: Mapping[str, object], key: str, path: Path) -> str:
    value = fields.get(key, "")
    if not isinstance(value, str):
        raise SkillParseError(f"{key} must be a string in {path}")
    return value


def _optional_string_field(
    fields: Mapping[str, object], key: str, path: Path
) -> str | None:
    value = fields.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SkillParseError(f"{key} must be a string in {path}")
    return value


def _metadata_field(fields: Mapping[str, object], path: Path) -> dict[str, str]:
    value = fields.get("metadata", {})
    if not isinstance(value, dict):
        raise SkillParseError(f"metadata must be a mapping in {path}")
    metadata: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise SkillParseError(f"metadata keys and values must be strings in {path}")
        metadata[key] = item
    return metadata


def _metadata_value(metadata: Mapping[str, str], key: str) -> str | None:
    value = metadata.get(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def _metadata_tuple(metadata: Mapping[str, str], key: str) -> tuple[str, ...]:
    value = metadata.get(key, "")
    return tuple(
        dict.fromkeys(item.strip() for item in re.split(r"[;|]", value) if item.strip())
    )


def _parse_key_value(line: str, path: Path) -> tuple[str, str]:
    if ":" not in line:
        raise SkillParseError(f"invalid frontmatter line in {path}: {line}")
    key, value = line.split(":", 1)
    key = key.strip()
    if not key:
        raise SkillParseError(f"blank frontmatter key in {path}")
    return key, value.strip()


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _extract_references(body: str) -> tuple[str, ...]:
    references: list[str] = []
    for match in _REFERENCE.finditer(body):
        target = next((item for item in match.groups() if item), "")
        normalized = target.strip().replace("\\", "/")
        if normalized.startswith(("http://", "https://", "#")):
            continue
        if normalized.startswith(("references/", "scripts/", "assets/")):
            references.append(normalized)
    return tuple(dict.fromkeys(references))


def _optional_directories(skill_dir: Path) -> tuple[str, ...]:
    return tuple(
        name
        for name in ("scripts", "references", "assets")
        if (skill_dir / name).is_dir()
    )


def _root_files(skill_dir: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                path.name
                for path in skill_dir.iterdir()
                if path.is_file() and path.name != "SKILL.md"
            ),
            key=str.casefold,
        )
    )
