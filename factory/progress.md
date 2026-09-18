# Factory Progress

## 2026-07-27

- Bootstrapped the governed factory contract.
- Added phase artifacts, skill suite plan, and validation expectations.
- Changed future execution semantics from unattended work to
  `BACKGROUND_SHIFT`: computer-on, user-visible, interruptible background work.
- Deferred background worker implementation and proof video generation.

## 2026-08-04

- Accepted the full system audit diff plan for staged implementation.
- Started with bounded JSONL destination verification hardening.
- Preserved deterministic trading authority and local advisory-only Qwen scope.
- Completed bounded JSONL persistence, compact audit, component health,
  accounting tail diagnostics, interaction-output reduction, safe 5S cleanup,
  validation checkpoint, and local Qwen routing slices.
- Restarted and verified all approved resident service tasks; local Qwen is a
  visible scheduled task with a 30-second heartbeat.
- Full quality gate passed with 1533 tests and 90.05% coverage.
- Accounting collectors recovered to `CLEAN`; startup and local advisory report
  `READY` while trading-domain blockers remain fail-closed.
- Advanced to review; independent fresh review remains pending.

## 2026-08-08

- Replaced one-shot/IPv4-only Ollama startup checks with shared API-first,
  IPv4/IPv6-safe, bounded-retry supervision.
- Verified and removed only the duplicate provider owned by the old prompter;
  retained the Ollama App provider and restarted the visible Qwen task.
- Added a human-in-the-loop, read-only local Qwen workbench with bounded repo
  evidence, exact `qwen3:8b` enforcement, output integrity gates, and verified
  JSON evidence.
- Real local Turkish Qwen generation passed; full gate passed with 1591 tests
  and 90.16% coverage.
- Independent fresh review and trading-domain evidence blockers remain open.
