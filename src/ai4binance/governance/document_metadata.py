"""Shared scalar document metadata parsing without validator dependencies."""

from pathlib import Path


def clean_metadata_value(value: str) -> str:
    return value.strip().strip("\"'`")


def read_document_frontmatter(path: Path) -> dict[str, str] | None:
    """Read the existing scalar format; preserve missing and invalid boundaries."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if text.startswith("---\r\n"):
        offset = 5
    elif text.startswith("---\n"):
        offset = 4
    else:
        return None
    end = text.find("\n---", offset)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for raw_line in text[offset:end].splitlines():
        if raw_line[:1].isspace():
            continue
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = clean_metadata_value(value)
    return fields
