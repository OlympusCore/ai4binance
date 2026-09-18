# Factory Log

Append concise operational notes here. Do not paste secrets, wallet details,
private API responses, or large logs.

## 2026-07-27

- Factory bootstrap approved by user.
- Scope limited to contracts, skills, validation, and documentation.
- Factory execution model changed to `BACKGROUND_SHIFT` instead of unattended
  work.

## 2026-08-04

- User approved stepwise implementation of the full system hardening plan.
- Local LLM target is loopback Ollama `qwen3:8b`; hosted provider routing is
  forbidden for this work order.
- First implementation slice: bounded JSONL destination read-back.
- JSONL append verification benchmark on a 773,611,127-byte audit file: 3.748 ms.
- System-report interactive runtime reduced from 50,115 ms to 9,987 ms by
  persisting full detail and printing a bounded summary.
- Safe 5S apply removed one reproducible cache; 18 ACL-blocked stale test-temp
  folders were preserved without ownership takeover.
- Ollama/qwen proof returned `LOCAL_QWEN_OK`; all scheduled service tasks report
  `Running` and startup infrastructure issues are empty.
- Full quality gate passed: 1533 tests, total coverage 90.05%.
- Final system report: startup `READY`, local advisory `READY`, accounting
  `CLEAN`; runtime remains `RUNNING_WITH_BLOCKERS` for inventory/risk/OOS data.

## 2026-08-08

- User approved implementation of the local Qwen stability and workbench slice.
- Live ownership proof found Ollama App PID 9492 and duplicate old-prompter child
  PID 18216. Only the verified duplicate was stopped.
- Persisted user `OLLAMA_HOST=127.0.0.1:11434`; wildcard Ollama App ownership
  was replaced by one task-owned loopback provider.
- Restarted `AI4BINANCE-Qwen3-Prompter`; final state is one loopback listener,
  task `Running`, health `RUNNING`, and exact model `qwen3:8b`.
- Local workbench real proof produced a destination-verified UTF-8 Turkish
  response with `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` safety stamps.
- Full quality gate passed: 1591 tests, total coverage 90.16%.
