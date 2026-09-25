# Public Showcase Publication Boundary

`public_manifest.yaml` is the canonical public-export allowlist. Everything
outside `allowed_paths` is denied by default. Entries in `denied_paths` are a
second, non-overridable defense layer.

The export remains local-only until its selected files have passed
sanitization, secret scanning, diff review, and explicit human approval.

The internal public-market gateway at
`src/ai4binance/cli/market_gateway.py` owns bounded public-data access and
fail-closed transport reporting. Verified JSON persistence remains centralized
in `src/ai4binance/infrastructure/persistence/safe_json.py`; callers must use
its atomic write and read-back verification boundary instead of creating a
parallel persistence path. Cross-process event persistence uses the bounded
exclusive-lock implementation in `src/ai4binance/events/file_lock.py`, including
retryable Windows contention and a deterministic timeout. These implementation
surfaces remain `CLOSED` and cannot grant publication, promotion, deployment,
or trading authority.

`src/ai4binance/ops/public_showcase.py` enforces the local staging boundary and
invokes the repository-pinned Gitleaks binary with a fixed argument vector,
`shell=False`, bounded timeout handling, and redacted output. This scanner
boundary is report/block only and never grants publication, promotion,
deployment, or trading authority.

## Disclosure Policy

| Level | Public treatment |
| --- | --- |
| OPEN | Architecture philosophy, governance concepts, ontology structure, decision lifecycle, evidence model, contracts, diagrams, and synthetic examples. |
| PARTIAL | Schemas, interfaces, event contracts, simplified algorithms, and example tests only after manual curation. |
| CLOSED | Alpha generation, strategy implementation, weights, risk thresholds, parameter sets, optimization, execution internals, prompts, operational governance, research evidence, market datasets, and production configuration. |

`CLOSED` is the default. A path must be both explicitly allowlisted and outside
the defense-in-depth deny list before it can be staged for review.
