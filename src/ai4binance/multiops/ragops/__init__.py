"""RAGOps domain metadata and governed RAG pattern catalog."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.multiops.contracts import OpsCapability, OpsDomain

DOMAIN = OpsDomain.RAGOPS
CAPABILITIES = (
    OpsCapability.CORPUS_VERSION,
    OpsCapability.CHUNKING,
    OpsCapability.EMBEDDING,
    OpsCapability.RETRIEVAL_QUALITY,
    OpsCapability.SOURCE_LINEAGE,
)


class RagPatternId(StrEnum):
    BASIC_RAG = "basic_rag"
    METADATA_FILTERING = "metadata_filtering"
    QUERY_REWRITING = "query_rewriting"
    HYBRID_SEARCH = "hybrid_search"
    RERANKING = "reranking"
    MULTI_VECTOR_RETRIEVAL = "multi_vector_retrieval"
    QUERY_DECOMPOSITION = "query_decomposition"
    CONVERSATION_RAG = "conversation_rag"
    RETRIEVAL_AUGMENTED_SUMMARIZATION = "retrieval_augmented_summarization"
    STEP_BACK_RAG = "step_back_rag"
    ROUTING_RAG = "routing_rag"
    AGENTIC_RAG_ITERATIVE = "agentic_rag_iterative"
    SELF_CORRECTING_RAG = "self_correcting_rag"
    CITATION_AWARE_RAG = "citation_aware_rag"
    GUARDED_RAG = "guarded_rag"


class RagPatternImplementationStatus(StrEnum):
    IMPLEMENTED_LOCAL = "IMPLEMENTED_LOCAL"
    PARTIAL_LOCAL = "PARTIAL_LOCAL"
    DEFINED_RESEARCH_ONLY = "DEFINED_RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class RagPatternDefinition:
    pattern_id: RagPatternId
    display_name: str
    purpose: str
    use_when: tuple[str, ...]
    required_controls: tuple[str, ...]
    measurement_signals: tuple[str, ...]
    implementation_status: RagPatternImplementationStatus
    stopping_rule: str
    review_rule: str
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.display_name.strip() or not self.purpose.strip():
            raise ValueError("RAG pattern identity is required")
        for values in (
            self.use_when,
            self.required_controls,
            self.measurement_signals,
        ):
            _require_unique_nonblank("RAG pattern lists", values)
        if not self.stopping_rule.strip() or not self.review_rule.strip():
            raise ValueError("RAG pattern stop and review rules are required")
        if "HUMAN_REVIEW_REQUIRED" not in self.required_controls:
            raise ValueError("RAG pattern requires human review")
        if "LIVE_ORDER_BLOCKED" not in self.required_controls:
            raise ValueError("RAG pattern must keep live blocker visible")
        if self.promotion_status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("RAG patterns cannot promote or execute")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("RAG patterns must remain live blocked")


def build_rag_pattern_catalog() -> tuple[RagPatternDefinition, ...]:
    """Return the 15 governed RAG patterns in the production-reference order."""
    controls = (
        "SOURCE_ALLOWLIST_REQUIRED",
        "CITATION_REQUIRED",
        "HUMAN_REVIEW_REQUIRED",
        "LIVE_ORDER_BLOCKED",
    )
    quality = (
        "citation_coverage",
        "retrieval_score",
        "blocker_count",
        "freshness_days",
    )
    return (
        RagPatternDefinition(
            RagPatternId.BASIC_RAG,
            "Basic RAG",
            "Retrieve top-k approved local fragments and generate advisory context.",
            ("simple_fact_lookup", "small_local_corpus", "fast_advisory_context"),
            controls,
            quality,
            RagPatternImplementationStatus.IMPLEMENTED_LOCAL,
            "stop when top-k approved fragments are returned or retrieval is empty",
            "review retrieved citations before advisory synthesis",
        ),
        RagPatternDefinition(
            RagPatternId.METADATA_FILTERING,
            "Metadata Filtering",
            "Filter candidate fragments by source root, authority and classification.",
            ("source_scoped_query", "private_path_risk", "freshness_sensitive_context"),
            (*controls, "METADATA_FILTER_REQUIRED"),
            quality,
            RagPatternImplementationStatus.IMPLEMENTED_LOCAL,
            "stop when all metadata filters are applied deterministically",
            "review rejected filters and missing metadata as blockers",
        ),
        RagPatternDefinition(
            RagPatternId.QUERY_REWRITING,
            "Query Rewriting",
            "Normalize ambiguous user wording into bounded retrieval queries.",
            ("ambiguous_query", "synonym_expansion", "ticker_or_timeframe_aliases"),
            (*controls, "REWRITE_TRACE_REQUIRED"),
            (*quality, "rewrite_count"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after one deterministic rewrite set or ambiguity blocker",
            "review original and rewritten query pairs before retrieval",
        ),
        RagPatternDefinition(
            RagPatternId.HYBRID_SEARCH,
            "Hybrid Search",
            "Combine lexical and vector-style retrieval signals with stable fusion.",
            ("rare_terms", "long_tail_queries", "semantic_recall_gap"),
            (*controls, "FUSION_RULE_REQUIRED"),
            (*quality, "fusion_agreement"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after each retrieval channel returns or times out",
            "review channel disagreement before advisory synthesis",
        ),
        RagPatternDefinition(
            RagPatternId.RERANKING,
            "Reranking",
            "Reorder retrieved fragments with a bounded relevance rubric.",
            (
                "many_candidate_hits",
                "top_k_order_uncertain",
                "quality_sensitive_answer",
            ),
            (*controls, "RERANK_RUBRIC_REQUIRED"),
            (*quality, "rerank_delta"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after one bounded rerank pass",
            "review low confidence or large rank movement as blockers",
        ),
        RagPatternDefinition(
            RagPatternId.MULTI_VECTOR_RETRIEVAL,
            "Multi-Vector Retrieval",
            "Represent documents by multiple facets such as title, summary and chunks.",
            ("large_documents", "multi_aspect_evidence", "summary_chunk_split"),
            (*controls, "FACET_LINEAGE_REQUIRED"),
            (*quality, "facet_coverage"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after all approved facets are queried",
            "review facet collisions and missing lineage",
        ),
        RagPatternDefinition(
            RagPatternId.QUERY_DECOMPOSITION,
            "Query Decomposition",
            "Break multi-part questions into independently retrieved sub-queries.",
            ("multi_faceted_question", "comparison_request", "compound_blockers"),
            (*controls, "SUBQUERY_TRACE_REQUIRED"),
            (*quality, "subquery_coverage"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after each sub-query has evidence or a blocker",
            "review merge and deduplication before final synthesis",
        ),
        RagPatternDefinition(
            RagPatternId.CONVERSATION_RAG,
            "Conversation RAG",
            "Use bounded conversation context while preserving source-grounded "
            "retrieval.",
            ("follow_up_question", "context_continuity", "session_scoped_query"),
            (*controls, "CONVERSATION_CONTEXT_BUDGET_REQUIRED"),
            (*quality, "history_token_count"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop when bounded history plus retrieved evidence fits the budget",
            "review stale or private conversation context before reuse",
        ),
        RagPatternDefinition(
            RagPatternId.RETRIEVAL_AUGMENTED_SUMMARIZATION,
            "Retrieval-Augmented Summarization",
            "Summarize multiple retrieved documents with citation coverage.",
            ("what_happened_summary", "multi_doc_summary", "operator_brief"),
            (*controls, "SUMMARY_CLAIM_COVERAGE_REQUIRED"),
            (*quality, "summary_claim_coverage"),
            RagPatternImplementationStatus.PARTIAL_LOCAL,
            "stop when every summary claim has a source or blocker",
            "review unsupported claims and omitted blockers",
        ),
        RagPatternDefinition(
            RagPatternId.STEP_BACK_RAG,
            "Step-Back RAG",
            "Retrieve broad governing context before specific artifacts.",
            ("vague_question", "policy_context_needed", "architecture_assessment"),
            (*controls, "BROAD_CONTEXT_FIRST_REQUIRED"),
            (*quality, "broad_to_specific_trace"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop after broad context and specific evidence are both checked",
            "review broad-context drift before applying specifics",
        ),
        RagPatternDefinition(
            RagPatternId.ROUTING_RAG,
            "Routing RAG",
            "Route retrieval to the correct approved corpus or evidence source.",
            ("multiple_indexes", "tool_or_corpus_selection", "domain_specific_query"),
            (*controls, "ROUTE_TAXONOMY_REQUIRED"),
            (*quality, "route_confidence"),
            RagPatternImplementationStatus.PARTIAL_LOCAL,
            "stop after one route is selected or ambiguity is blocked",
            "review ambiguous and high-risk routes manually",
        ),
        RagPatternDefinition(
            RagPatternId.AGENTIC_RAG_ITERATIVE,
            "Agentic RAG (Iterative)",
            "Plan, retrieve, observe and repeat within a bounded research loop.",
            ("deep_research", "multi_step_investigation", "gap_driven_retrieval"),
            (*controls, "ITERATION_BUDGET_REQUIRED", "NO_AUTONOMOUS_ACTIONS"),
            (*quality, "iteration_count"),
            RagPatternImplementationStatus.DEFINED_RESEARCH_ONLY,
            "stop at iteration budget, failed gate or human-review point",
            "review every loop step; loop output is not execution authority",
        ),
        RagPatternDefinition(
            RagPatternId.SELF_CORRECTING_RAG,
            "Self-Correcting RAG",
            "Detect low-confidence retrieval and request safer retrieval or blockers.",
            ("low_score_hits", "empty_retrieval", "ambiguous_evidence"),
            (*controls, "QUALITY_GATE_REQUIRED"),
            (*quality, "correction_action"),
            RagPatternImplementationStatus.IMPLEMENTED_LOCAL,
            "stop when retrieval is correct, incorrect or ambiguous",
            "review ambiguous retrieval before advisory synthesis",
        ),
        RagPatternDefinition(
            RagPatternId.CITATION_AWARE_RAG,
            "Citation-Aware RAG",
            "Bind advisory output to source URI, hash and citation coverage.",
            ("audit_sensitive_answer", "source_required_report", "operator_brief"),
            (*controls, "CLAIM_TO_SOURCE_REQUIRED"),
            (*quality, "claim_source_binding"),
            RagPatternImplementationStatus.IMPLEMENTED_LOCAL,
            "stop when every accepted hit is cited or coverage blocker is raised",
            "review uncited evidence and unsupported claims",
        ),
        RagPatternDefinition(
            RagPatternId.GUARDED_RAG,
            "Guarded RAG",
            "Apply allow/deny policies to retrieval and generation boundaries.",
            ("private_data_risk", "prompt_injection_risk", "regulated_domain"),
            (*controls, "SECRET_SCAN_REQUIRED", "PRIVATE_PATH_BLOCK_REQUIRED"),
            (*quality, "guard_blocker_count"),
            RagPatternImplementationStatus.IMPLEMENTED_LOCAL,
            "stop at the first restricted source, unsafe authority or live gate risk",
            "review guard blockers before any downstream use",
        ),
    )


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if not values or len(set(values)) != len(values):
        raise ValueError(f"{name} must be non-empty and unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")


RAG_PATTERN_CATALOG = build_rag_pattern_catalog()

__all__ = [
    "CAPABILITIES",
    "DOMAIN",
    "RAG_PATTERN_CATALOG",
    "RagPatternDefinition",
    "RagPatternId",
    "RagPatternImplementationStatus",
    "build_rag_pattern_catalog",
]
