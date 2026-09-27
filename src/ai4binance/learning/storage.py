"""Atomic learning summary plus append-only audit persistence."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai4binance.learning.models import LearningSummary
from ai4binance.reporting import to_primitive
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class LearningStore:
    summary_path: Path
    audit_path: Path

    def save_cases(self, summary: LearningSummary) -> list[dict[str, object]]:
        """Verify existing cases and recover missing projections on every analysis."""
        case_refs: list[dict[str, object]] = []
        for case in summary.evidence_cases:
            path = self.summary_path.parent / "learning_cases" / f"{case.sha256}.json"
            source = json.loads(case.payload_json)
            decision = source.get("decision_evidence", {})
            # RAG indexes a bounded leading excerpt. Keep parameters before the
            # potentially large closed-candle factors, without dropping evidence.
            analysis_summary = {
                "symbol": source.get("symbol"),
                "market": source.get(
                    "market", "SPOT" if case.kind == "PAPER_POSITION" else None
                ),
                "quantity": source.get(
                    "quantity",
                    source.get("initial_quantity", source.get("proposed_quantity")),
                ),
                "leverage": source.get("leverage", source.get("proposed_leverage")),
                "entry": source.get("entry_price", source.get("proposed_entry")),
                "stop_loss": source.get(
                    "initial_stop_loss",
                    source.get("stop_loss", source.get("proposed_stop_loss")),
                ),
                "take_profit": source.get(
                    "initial_take_profit_levels",
                    source.get(
                        "proposed_take_profit_levels",
                        source.get("plan", {}).get("targets"),
                    ),
                ),
                "rr": source.get("planned_rr", source.get("proposed_rr")),
                "net_pnl": source.get("net_pnl", source.get("realized_pnl_usdt")),
                "forward_net_pnl": source.get("forward_net_pnl"),
                "counterfactual_result": source.get("counterfactual_result"),
                "direction_method": decision.get("direction_method"),
                "entry_method": decision.get("entry_method"),
                "parameter_methods": source.get("parameter_methods"),
            }
            payload = {
                "case_id": case.evidence_ref,
                "kind": case.kind,
                "tags": list(case.tags),
                "payload": source,
                "execution_allowed": False,
                "risk_change_allowed": False,
                "authority": "RESEARCH_ONLY",
                "execution_scope": "SIMULATED_RESEARCH",
            }
            previous_projection = payload.copy()
            payload["analysis_summary"] = analysis_summary
            needs_write = True
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != payload and existing != previous_projection:
                    raise ValueError("learning evidence case content mismatch")
                needs_write = existing != payload
            if needs_write:
                write_json_object_verified(
                    path,
                    payload,
                    blocker="LEARNING_CASE_DESTINATION_VERIFY_FAILED",
                    subject_id=case.evidence_ref,
                    indent=2,
                )
            case_refs.append(
                {
                    "evidence_ref": case.evidence_ref,
                    "kind": case.kind,
                    "path": f"learning_cases/{path.name}",
                }
            )
        return case_refs

    def save(self, summary: LearningSummary) -> None:
        # A successor must have been initialized explicitly; an invalid journal
        # never triggers automatic migration or recovery.
        if self.audit_path.with_suffix(".chained.jsonl").exists():
            audit_store = JsonlAuditStore.chained_successor(self.audit_path)
            audit_store.durable = True
        else:
            audit_store = JsonlAuditStore(
                self.audit_path, durable=True, tamper_evident=True
            )
        audit_store.verify_chain()
        primitive = cast(dict[str, object], to_primitive(summary))
        primitive["evidence_cases"] = self.save_cases(summary)
        # Publish the replaceable summary only after its audit evidence exists.
        audit_store.append_verified(
            AuditEvent(
                event_type="LEARNING_SUMMARY_CREATED",
                timestamp=summary.created_at,
                payload={"summary": primitive},
                snapshot_id=summary.summary_id,
            )
        )
        write_json_object_verified(
            self.summary_path,
            primitive,
            blocker="LEARNING_SUMMARY_DESTINATION_VERIFY_FAILED",
            subject_id=summary.summary_id,
            indent=2,
        )
