from __future__ import annotations

import gc
import importlib
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("package", "extra", "minimum", "maximum"),
    [("mako", "research", (1, 4, 3), 2), ("multidict", "voice", (6, 9, 1), 7)],
)
def test_dependency_security_floors(
    package: str, extra: str, minimum: tuple[int, ...], maximum: int
) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    floor = ".".join(str(part) for part in minimum)
    assert (
        f"{package}>={floor},<{maximum}"
        in project["project"]["optional-dependencies"][extra]
    )
    packages = [item for item in lock["package"] if item["name"] == package]
    assert packages
    for item in packages:
        assert tuple(int(part) for part in item["version"].split(".")) >= minimum


@pytest.mark.parametrize("directory_kind", ["relative", "absolute"])
@pytest.mark.parametrize(
    "uri",
    [
        "../sentinel.txt",
        "//../sentinel.txt",
        "\\..\\sentinel.txt",
        "C:/../../sentinel.txt",
        "C:\\..\\..\\sentinel.txt",
        "d:/../../sentinel.txt",
    ],
)
def test_mako_reported_traversals_are_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory_kind: str, uri: str
) -> None:
    pytest.importorskip("mako", reason="Requires the research extra")
    lookup_module = importlib.import_module("mako.lookup")
    exceptions = importlib.import_module("mako.exceptions")
    templates = tmp_path / "templates"
    templates.mkdir()
    (tmp_path / "sentinel.txt").write_text("TEST_ONLY_OUTSIDE", encoding="utf-8")
    (templates / "good.html").write_text("Hello ${name}!", encoding="utf-8")
    monkeypatch.chdir(templates)
    directory = "." if directory_kind == "relative" else str(templates)
    lookup = lookup_module.TemplateLookup(directories=[directory])
    assert lookup.get_template("good.html").render(name="world") == "Hello world!"
    with pytest.raises(exceptions.TemplateLookupException):
        lookup.get_template(uri)


@pytest.mark.parametrize("class_name", ["MultiDict", "CIMultiDict"])
@pytest.mark.parametrize(
    "operation", ["reverse_union", "subtraction", "forward_union", "intersection"]
)
def test_multidict_items_operations_release_references(
    class_name: str, operation: str
) -> None:
    module = pytest.importorskip("multidict", reason="Requires the voice extra")
    mapping = getattr(module, class_name)
    value, other_value = object(), object()
    items = mapping([("Header", value)])
    operand = {("Other", other_value)}
    expected = {
        "reverse_union": {("Header", value), ("Other", other_value)},
        "subtraction": {("Header", value)},
        "forward_union": {("Header", value), ("Other", other_value)},
        "intersection": set(),
    }[operation]
    gc.collect()
    before = (
        sys.getrefcount(value),
        sys.getrefcount(other_value),
        sys.getrefcount(items),
    )
    for _ in range(32):
        if operation == "reverse_union":
            result = operand | items.items()
        elif operation == "subtraction":
            result = items.items() - operand
        elif operation == "forward_union":
            result = items.items() | operand
        else:
            result = items.items() & operand
        assert result == expected
        del result
    gc.collect()
    assert (
        sys.getrefcount(value),
        sys.getrefcount(other_value),
        sys.getrefcount(items),
    ) == before


def test_multidict_duplicate_header_semantics_are_preserved() -> None:
    module = pytest.importorskip("multidict", reason="Requires the voice extra")
    headers = module.CIMultiDict([("X-Header", "first"), ("x-header", "second")])
    proxy = module.CIMultiDictProxy(headers)
    assert proxy["X-HEADER"] == "first"
    assert proxy.getall("x-header") == ["first", "second"]
    assert list(proxy.items()) == [("X-Header", "first"), ("x-header", "second")]
