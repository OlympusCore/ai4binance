"""Deterministic generated Markdown views for authority-graph evidence."""

from __future__ import annotations

from pathlib import Path

from ai4binance.governance.authority.graph import AuthorityGraph

_GENERATED_DOCUMENT_ID = "AI4B-GOV-AUTHORITY-GRAPH-VIEW-001"
_RUNTIME_ROOT_NAME = "runtime"


def render_authority_graph_markdown(graph: AuthorityGraph) -> str:
    """Render a non-authoritative Markdown view from declared graph metadata."""
    lines = [
        "---",
        f"document_id: {_GENERATED_DOCUMENT_ID}",
        "title: Authority Graph Generated View",
        "document_type: REFERENCE",
        f"source_graph_id: {graph.graph_id}",
        f"source_graph_version: {graph.version}",
        "authority_level: INFORMATIONAL",
        "authority_effect: EVIDENCE_ONLY",
        "content_role: GENERATED",
        "source_of_truth: false",
        "execution_allowed: false",
        "live_eligibility_status: LIVE_ORDER_BLOCKED",
        "---",
        "",
        "# Authority Graph Generated View",
        "",
        "This generated view is evidence-only. It does not define authority, grant "
        "approval, authorize promotion, or permit execution.",
        "",
        "## Graph Status",
        "",
        f"- Graph ID: `{_markdown_code(graph.graph_id)}`",
        f"- Version: `{_markdown_code(graph.version)}`",
        f"- Status: `{_markdown_code(graph.status)}`",
        "- Live eligibility: `LIVE_ORDER_BLOCKED`",
        "",
        "## Nodes",
        "",
        "| Node ID | Document ID | Canonical Path | Layer | Effect | Scope | SoT |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_node_rows(graph))
    lines.extend(
        (
            "",
            "## Relationships",
            "",
            "| Edge ID | From | Relation | To | Family |",
            "| --- | --- | --- | --- |",
        )
    )
    lines.extend(_edge_rows(graph))
    lines.extend(
        (
            "",
            "## Safety Boundary",
            "",
            "- This artifact is generated from the declared authority graph.",
            "- Conflicts and metadata drift remain fail-closed.",
            "- Live eligibility remains `LIVE_ORDER_BLOCKED`.",
            "",
        )
    )
    return "\n".join(lines)


def write_runtime_authority_graph_markdown(
    graph: AuthorityGraph, root: Path, output_path: Path
) -> Path:
    """Write a generated view only below the repository runtime root.

    Generated views deliberately cannot overwrite governed Markdown under
    ``docs/``. Callers must provide a repository-relative ``runtime/*.md``
    destination.
    """
    resolved_root = root.resolve()
    if output_path.is_absolute():
        resolved_output = output_path.resolve()
    else:
        resolved_output = (resolved_root / output_path).resolve()
    try:
        relative_output = resolved_output.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            "authority graph output must stay inside the repository"
        ) from error
    if not relative_output.parts or relative_output.parts[0] != _RUNTIME_ROOT_NAME:
        raise ValueError("authority graph output must stay below runtime")
    if resolved_output.suffix != ".md":
        raise ValueError("authority graph output must use the .md extension")

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(render_authority_graph_markdown(graph), encoding="utf-8")
    return resolved_output


def _node_rows(graph: AuthorityGraph) -> tuple[str, ...]:
    return tuple(
        "| "
        + " | ".join(
            (
                _markdown_table(node.node_id),
                _markdown_table(node.document_id),
                _markdown_table(node.canonical_path),
                _markdown_table(node.authority_layer),
                _markdown_table(node.authority_effect),
                _markdown_table(node.authority_scope),
                _markdown_table(str(node.source_of_truth).lower()),
            )
        )
        + " |"
        for node in sorted(graph.nodes, key=lambda item: item.node_id)
    )


def _edge_rows(graph: AuthorityGraph) -> tuple[str, ...]:
    return tuple(
        "| "
        + " | ".join(
            (
                _markdown_table(edge.edge_id),
                _markdown_table(edge.from_node_id),
                _markdown_table(edge.relation.value),
                _markdown_table(edge.to_node_id),
                _markdown_table(edge.edge_family.value),
            )
        )
        + " |"
        for edge in sorted(graph.edges, key=lambda item: item.edge_id)
    )


def _markdown_table(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _markdown_code(value: str) -> str:
    return value.replace("`", "\\`").replace("\n", " ")
