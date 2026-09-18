"""Deterministic progressive disclosure for governed tool metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai4binance.governance.tool_policy import ToolDescriptor, ToolSideEffect

_WORD = re.compile(r"\w+", re.UNICODE)
_NON_DISCLOSABLE = frozenset(
    {
        ToolSideEffect.EXTERNAL_WRITE,
        ToolSideEffect.FINANCIAL,
        ToolSideEffect.FORBIDDEN,
    }
)


def _terms(value: str) -> set[str]:
    return {term.casefold() for term in _WORD.findall(value)}


@dataclass(frozen=True, slots=True)
class ToolSelection:
    query: str
    selected: tuple[ToolDescriptor, ...] = ()
    schema_tokens: int = 0
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_tokens < 0:
            raise ValueError("tool selection schema tokens cannot be negative")
        if not self.selected and not self.blockers:
            raise ValueError("empty tool selection requires blockers")


class ToolRegistry:
    def __init__(self, descriptors: tuple[ToolDescriptor, ...]) -> None:
        by_name = {descriptor.name: descriptor for descriptor in descriptors}
        if len(by_name) != len(descriptors):
            raise ValueError("tool descriptors must be unique")
        self._descriptors = by_name

    def require(self, name: str) -> ToolDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise PermissionError("TOOL_NOT_REGISTERED") from exc

    def shortlist(
        self,
        query: str,
        *,
        project: str,
        max_tools: int = 4,
        max_schema_tokens: int = 512,
    ) -> ToolSelection:
        if not 1 <= max_tools <= 16:
            raise ValueError("max_tools is invalid")
        if max_schema_tokens < 0:
            raise ValueError("max_schema_tokens cannot be negative")
        query_terms = _terms(query)
        if not query_terms:
            return ToolSelection(query=query, blockers=("NO_TOOL_MATCH",))

        ranked: list[tuple[int, ToolDescriptor]] = []
        for descriptor in self._descriptors.values():
            if project not in descriptor.allowed_projects:
                continue
            if descriptor.side_effect in _NON_DISCLOSABLE:
                continue
            score = 0
            if descriptor.name.casefold() in query.casefold():
                score += 100
            score += 20 * len(query_terms & {tag.casefold() for tag in descriptor.tags})
            score += 10 * len(query_terms & _terms(descriptor.name))
            score += 2 * len(query_terms & _terms(descriptor.description))
            if score:
                ranked.append((score, descriptor))

        selected: list[ToolDescriptor] = []
        schema_tokens = 0
        for _, descriptor in sorted(ranked, key=lambda item: (-item[0], item[1].name)):
            if len(selected) >= max_tools:
                break
            if schema_tokens + descriptor.schema_tokens > max_schema_tokens:
                continue
            selected.append(descriptor)
            schema_tokens += descriptor.schema_tokens
        return ToolSelection(
            query=query,
            selected=tuple(selected),
            schema_tokens=schema_tokens,
            blockers=() if selected else ("NO_TOOL_MATCH",),
        )
