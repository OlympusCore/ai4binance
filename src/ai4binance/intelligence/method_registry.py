"""Single offline registry for reviewed methods, rules and coverage projections.

Registry membership describes implementation and provenance. It never approves
a method, evaluates source text, imports a registry-selected callable, or grants
trading authority. Unimplemented catalog entries cannot produce lineage.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import unquote, urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from ai4binance.intelligence.method_lineage import MethodLineage
from ai4binance.schema_validation import OfflineSchemaRegistry

REGISTRY_PATH = Path("docs/registries/registry_trading_intelligence.yaml")
SCHEMA_ID = "urn:ai4binance:schema:registries:trading-intelligence:1.0.0"
Text = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]
Version = Annotated[StrictStr, Field(pattern=r"^\d+\.\d+\.\d+$")]


class RegistryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceBibliography(RegistryRecord):
    """Reviewed source metadata, without source-content or performance approval."""

    title: Text
    organization: Text
    author: Text | None
    source_family: Text
    primary_or_secondary: Literal["PRIMARY", "SECONDARY", "IMPLEMENTATION_REFERENCE"]
    publication_date: Text | None
    source_version: Text | None
    accessed_at: datetime
    licensing_notes: Text
    conflict_notes: Text

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.accessed_at.utcoffset() is None:
            raise ValueError("source access timestamp must be timezone-aware")
        return self


class SourceDefinition(RegistryRecord):
    source_id: Text
    locator: Text
    source_type: Literal["REPOSITORY", "EXTERNAL_REFERENCE"]
    verification: Literal["CODE_INSPECTED", "REFERENCE_ONLY"]
    revision: Text | None
    content_sha256: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")] | None
    notes: Text
    bibliography: SourceBibliography | None = None


class RuleSemantics(RegistryRecord):
    """Descriptive rule dependencies; never an executable expression or authority."""

    prerequisite_rules: tuple[Text, ...] = ()
    conflicting_rules: tuple[Text, ...] = ()
    parameter_refs: tuple[Text, ...] = ()
    invalidation_effect: Text
    authority: Literal["EVIDENCE_ONLY"] = "EVIDENCE_ONLY"


class MethodRuleStages(RegistryRecord):
    """References to the existing rule registry, separated by lifecycle purpose."""

    anchor: tuple[Text, ...] = ()
    formation: tuple[Text, ...] = ()
    confirmation: tuple[Text, ...] = ()
    invalidation: tuple[Text, ...] = ()
    failure: tuple[Text, ...] = ()
    target: tuple[Text, ...] = ()


class RuleDefinition(RegistryRecord):
    rule_id: Text
    version: Version
    rule_type: Literal[
        "AI4BINANCE_IMPLEMENTATION_RULE",
        "SOURCE_DEFINITION",
        "SOURCE_RULE",
        "SOURCE_GUIDELINE",
        "INDUSTRY_CONVENTION",
        "EMPIRICAL_FINDING",
        "AI4BINANCE_CANONICAL_RULE",
        "AI4BINANCE_VALIDATION_RULE",
        "AI4BINANCE_RISK_RULE",
    ]
    statement: Text
    implementation_ref: Text | None
    source_ids: tuple[Text, ...] = Field(min_length=1)
    test_refs: tuple[Text, ...]
    applicability: Text = "Research-only implementation; not a universal market rule."
    tolerance_policy: Text = (
        "Exact implementation constants; not empirically calibrated."
    )
    ambiguity: Text = "Method-level OOS evidence is unavailable."
    semantics: RuleSemantics | None = None


class SourceReview(RegistryRecord):
    """Dated comparison, separate from a source-content or empirical attestation."""

    source_id: Text
    reviewed_at: datetime
    finding: Text
    implementation_consequence: Text

    @model_validator(mode="after")
    def validate_timestamp(self) -> Self:
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("source review timestamp must be timezone-aware")
        return self


class ReferenceChapter(RegistryRecord):
    """Reviewed chapter interpretation; absent fields remain explicit research gaps."""

    bullish_interpretation: Text | None = None
    bearish_interpretation: Text | None = None
    neutral_interpretation: Text | None = None
    multi_timeframe_behavior: Text | None = None
    support_resistance_interaction: Text | None = None
    volume_interaction: Text | None = None
    volatility_interaction: Text | None = None
    derivatives_context: Text | None = None
    fibonacci_relationships: Text | None = None
    target_measurement: Text | None = None
    structural_invalidation: Text | None = None
    common_misidentifications: Text | None = None
    implementation_notes: Text | None = None
    research_backtest_notes: Text | None = None
    regime_sensitivity: Text | None = None
    source_conflicts: Text | None = None
    canonical_interpretation: Text | None = None


class MethodReference(RegistryRecord):
    """Explicit interpretation and limitations for the generated reference manual."""

    definition: Text
    purpose: Text
    origin_or_school: Text
    standardization_status: Literal[
        "LOCAL_IMPLEMENTATION", "SOURCE_SPECIFIC", "NOT_VERIFIED"
    ]
    market_context: tuple[Text, ...] = Field(min_length=1)
    direction_semantics: Text
    timeframe_semantics: Text
    known_failure_modes: tuple[Text, ...] = Field(min_length=1)
    ambiguity_notes: Text
    chapter: ReferenceChapter | None = None


class MethodDefinition(RegistryRecord):
    method_id: Text
    version: Version
    rule_set_version: Version
    family: Text
    canonical_name: Text
    implementation_status: Literal["IMPLEMENTED", "PARTIAL", "CATALOG_ONLY"]
    module: Text | None
    owner: Text | None
    rule_ids: tuple[Text, ...]
    source_ids: tuple[Text, ...]
    input_requirements: tuple[Text, ...] = Field(min_length=1)
    markets: tuple[Literal["SPOT", "USD_M_FUTURES"], ...] = Field(min_length=1)
    lifecycle_scope: Literal["PATTERN", "CONTEXT", "OPPORTUNITY"]
    limitations: Text
    validation_status: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    oos_status: Literal["METHOD_LEVEL_OOS_NOT_VERIFIED"] = (
        "METHOD_LEVEL_OOS_NOT_VERIFIED"
    )
    governance_status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    reference: MethodReference | None = None
    rule_stages: MethodRuleStages | None = None


class FamilyCoverage(RegistryRecord):
    family: Text
    module: Text
    owner: Text
    implemented: tuple[Text, ...]
    missing: tuple[Text, ...]
    decision_role: Text
    limitations: Text
    tests: tuple[Text, ...]
    source_ids: tuple[Text, ...]


class ScopeDefinition(RegistryRecord):
    family: Text
    status: Literal["IMPLEMENTED", "PARTIAL", "CATALOG_ONLY", "SOURCE_UNVERIFIED"]
    method_ids: tuple[Text, ...] = Field(min_length=1)
    notes: Text


class MethodAlias(RegistryRecord):
    alias: Text
    context: Text
    method_id: Text


class MethodInteraction(RegistryRecord):
    left: Text
    right: Text
    relationship: Literal["SHARED_INPUT", "SHARED_PIVOTS", "CONTEXT_ONLY"]
    independence_status: Literal["NOT_MEASURED"] = "NOT_MEASURED"


class TradingMethodRegistry(RegistryRecord):
    registry_id: Literal["AI4B-TRADING-METHODS-001"]
    version: Version
    source_of_truth: Literal[True]
    source_of_truth_scope: Literal["trading_method_definitions"]
    authority_effect: Literal["EVIDENCE_ONLY"]
    baseline_commit: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{40}$")]
    execution_allowed: Literal[False]
    promotion_status: Literal["RESEARCH_ONLY"]
    live_eligibility_status: Literal["LIVE_ORDER_BLOCKED"]
    sources: tuple[SourceDefinition, ...] = Field(min_length=1)
    rules: tuple[RuleDefinition, ...] = Field(min_length=1)
    methods: tuple[MethodDefinition, ...] = Field(min_length=1)
    coverage: tuple[FamilyCoverage, ...] = Field(min_length=1)
    scope: tuple[ScopeDefinition, ...] = Field(min_length=1)
    aliases: tuple[MethodAlias, ...]
    interactions: tuple[MethodInteraction, ...]
    source_reviews: tuple[SourceReview, ...] = ()

    @model_validator(mode="after")
    def validate_links(self) -> Self:
        sources = _unique(self.sources, "source_id")
        rules = _unique(self.rules, "rule_id")
        methods = _unique(self.methods, "method_id")
        _unique(self.coverage, "family")
        _unique(self.scope, "family")
        self._validate_sources()
        self._validate_method_links(rules, sources)
        self._validate_rule_dependencies(rules)
        self._validate_aliases(methods)
        self._validate_coverage()
        _unique(self.source_reviews, "source_id")
        _references(tuple(row.source_id for row in self.source_reviews), sources)
        for rule in self.rules:
            _references(rule.source_ids, sources)
            for path in rule.test_refs:
                _relative_path(path)
        for scope in self.scope:
            _references(scope.method_ids, methods)
            if any(self.method(key).family != scope.family for key in scope.method_ids):
                raise ValueError("scope cannot claim methods from another family")
        scoped_methods = {key for scope in self.scope for key in scope.method_ids}
        if methods != scoped_methods:
            raise ValueError("orphan method must belong to its declared family scope")
        used_rules = {key for method in self.methods for key in method.rule_ids}
        if rules != used_rules:
            raise ValueError("orphan rule must be referenced by a registered method")
        interactions: set[tuple[str, str]] = set()
        for edge in self.interactions:
            _references((edge.left, edge.right), methods)
            pair = (min(edge.left, edge.right), max(edge.left, edge.right))
            if pair in interactions:
                raise ValueError("duplicate undirected method interaction")
            interactions.add(pair)
        return self

    def _validate_rule_dependencies(self, known: set[str]) -> None:
        pending: dict[str, set[str]] = {}
        for rule in self.rules:
            semantics = rule.semantics
            if semantics is None:
                continue
            required = set(semantics.prerequisite_rules)
            conflicts = set(semantics.conflicting_rules)
            _references(
                semantics.prerequisite_rules + semantics.conflicting_rules, known
            )
            if rule.rule_id in required | conflicts or required & conflicts:
                raise ValueError("rule cannot require itself or a conflicting rule")
            if len(required) != len(semantics.prerequisite_rules) or len(
                conflicts
            ) != len(semantics.conflicting_rules):
                raise ValueError("duplicate rule dependency")
            pending[rule.rule_id] = required
        resolved = known - pending.keys()
        while pending:
            ready = {
                key for key, dependencies in pending.items() if dependencies <= resolved
            }
            if not ready:
                raise ValueError("cyclic rule prerequisites")
            resolved.update(ready)
            for key in ready:
                pending.pop(key)

    def _validate_coverage(self) -> None:
        for row in self.coverage:
            method = self.method(row.family)
            if (row.module, row.owner) != (method.module, method.owner):
                raise ValueError("coverage owner must match the canonical method")
            _references(row.source_ids, set(method.source_ids))
            if set(row.implemented) & set(row.missing):
                raise ValueError("coverage cannot be implemented and missing")

    def _validate_sources(self) -> None:
        for source in self.sources:
            if source.source_type == "REPOSITORY":
                if source.verification != "CODE_INSPECTED" or not source.content_sha256:
                    raise ValueError("repository sources require inspected content")
                _relative_path(source.locator)
            elif source.verification != "REFERENCE_ONLY" or source.content_sha256:
                raise ValueError("external references cannot claim verified content")
            else:
                _external_reference_url(source.locator)

    def _validate_method_links(self, rules: set[str], sources: set[str]) -> None:
        for method in self.methods:
            _references(method.rule_ids, rules)
            if method.rule_stages is not None:
                for refs in method.rule_stages.model_dump().values():
                    _references(refs, set(method.rule_ids))
                    if len(refs) != len(set(refs)):
                        raise ValueError("duplicate method stage rule")
            _references(method.source_ids, sources)
            if method.implementation_status != "CATALOG_ONLY" and not (
                method.module and method.owner and method.rule_ids and method.source_ids
            ):
                raise ValueError("implemented methods require owner, rules and sources")
            if method.implementation_status == "CATALOG_ONLY" and (
                method.module or method.owner
            ):
                raise ValueError(
                    "catalog methods cannot claim implementation ownership"
                )

    def _validate_aliases(self, methods: set[str]) -> None:
        aliases: set[tuple[str, str]] = set()
        for alias in self.aliases:
            key = (alias.context, alias.alias.casefold())
            if key in aliases or alias.method_id not in methods:
                raise ValueError("alias must have one existing contextual target")
            aliases.add(key)

    def method(self, method_id: str) -> MethodDefinition:
        for method in self.methods:
            if method.method_id == method_id:
                return method
        raise ValueError(f"unknown method: {method_id}")

    def lineage(
        self, method_id: str, version: str, rule_set_version: str
    ) -> MethodLineage:
        method = self.method(method_id)
        if method.implementation_status == "CATALOG_ONLY":
            raise ValueError("catalog method cannot produce observations")
        if (method.version, method.rule_set_version) != (version, rule_set_version):
            raise ValueError("unknown method or rule set version")
        rules = tuple(rule for rule in self.rules if rule.rule_id in method.rule_ids)
        source_ids = set(method.source_ids).union(*(rule.source_ids for rule in rules))
        sources = tuple(
            source for source in self.sources if source.source_id in source_ids
        )
        definition = {
            "method": _definition_payload(method),
            "rules": [
                _definition_payload(rule)
                for rule in sorted(rules, key=lambda r: r.rule_id)
            ],
            "sources": [
                source.model_dump(
                    mode="json",
                    exclude={"bibliography"} if source.bibliography is None else set(),
                )
                for source in sorted(sources, key=lambda s: s.source_id)
            ],
        }
        digest = sha256(
            json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return MethodLineage(
            method_id,
            version,
            rule_set_version,
            self.version,
            digest,
            tuple(sorted(f"{rule.rule_id}@{rule.version}" for rule in rules)),
            tuple(sorted(source_ids)),
        )

    def validate_lineage(self, lineage: MethodLineage) -> None:
        expected = self.lineage(
            lineage.method_id, lineage.method_version, lineage.rule_set_version
        )
        if lineage != expected:
            raise ValueError("method lineage does not match the registered definition")

    def snapshot_payload(self) -> dict[str, object]:
        """Embed the exact offline definitions used at decision time for replay."""
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return {"definition": payload, "sha256": sha256(encoded.encode()).hexdigest()}


def _definition_payload(record: MethodDefinition | RuleDefinition) -> dict[str, object]:
    """Do not retroactively add optional metadata to archived lineage hashes."""
    payload = record.model_dump(mode="json")
    for name in ("reference", "rule_stages", "semantics"):
        if payload.get(name) is None:
            payload.pop(name, None)
    reference = payload.get("reference")
    if isinstance(reference, dict) and reference.get("chapter") is None:
        reference.pop("chapter", None)
    return payload


def restore_registry_snapshot(payload: Mapping[str, object]) -> TradingMethodRegistry:
    """Validate archived definitions without consulting the current mutable registry."""
    encoded = json.dumps(
        payload.get("definition"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if sha256(encoded.encode()).hexdigest() != payload.get("sha256"):
        raise ValueError("archived method registry digest mismatch")
    return TradingMethodRegistry.model_validate(payload.get("definition"))


def _unique(records: tuple[RegistryRecord, ...], key: str) -> set[str]:
    values = tuple(str(getattr(record, key)) for record in records)
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate registry identity: {key}")
    return set(values)


def _references(values: tuple[str, ...], known: set[str]) -> None:
    if len(values) != len(set(values)) or not set(values) <= known:
        raise ValueError("duplicate or dangling registry references")


def _relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("registry paths must be repository-relative")
    return path


def _external_reference_url(value: str) -> None:
    """Validate passive source links locally without resolving or fetching them."""
    error = "external source requires a safe absolute HTTP(S) reference URL"
    if any(char.isspace() or char in "()[]<>\\\"'`" for char in value) or any(
        ord(char) < 32 or 127 <= ord(char) <= 159 for char in unquote(value)
    ):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname and parsed.hostname.strip("."))
            and "%" not in parsed.netloc
            and parsed.username is None
            and parsed.password is None
        )
        # Accessing the port also rejects malformed and out-of-range ports.
        _ = parsed.port
    except ValueError:
        raise ValueError(error) from None
    if not valid:
        raise ValueError(error)


def load_method_registry(path: Path | None = None) -> TradingMethodRegistry:
    root = Path(__file__).resolve().parents[3]
    registry_path = path or root / REGISTRY_PATH
    text = registry_path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("method registry exceeds its input bound")
    _validate_yaml(yaml.compose(text), set())
    payload = yaml.safe_load(text)
    OfflineSchemaRegistry.from_directory(root / "schemas/registries").validate(
        SCHEMA_ID, payload
    )
    return TradingMethodRegistry.model_validate(payload)


def _validate_yaml(node: yaml.Node | None, seen: set[int]) -> None:
    """Reject duplicate keys and aliases before a YAML parser can hide them."""
    if node is None:
        raise ValueError("method registry is empty")
    if id(node) in seen:
        raise ValueError("method registry YAML aliases are not supported")
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        keys: set[str] = set()
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.value in keys:
                raise ValueError("duplicate or non-scalar registry YAML key")
            keys.add(key.value)
            _validate_yaml(value, seen)
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            _validate_yaml(child, seen)


@lru_cache(maxsize=1)
def current_method_registry() -> TradingMethodRegistry:
    """Pin one immutable registry per process; a revision needs a new process."""
    return load_method_registry()


def recorded_lineage(metadata: Mapping[str, object]) -> MethodLineage | None:
    """Validate explicit new observations; absence remains legacy unrecorded."""
    if "method_lineage" not in metadata:
        return None
    lineage = MethodLineage.from_payload(metadata["method_lineage"])
    current_method_registry().validate_lineage(lineage)
    return lineage
