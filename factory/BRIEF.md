# Factory Brief

## Product Intent

Create a governed AI software factory for AI4BINANCE that turns user-approved
ideas into small, testable, reviewable work orders without granting autonomous
live trading authority.

## User Need

The user wants less all-day prompt feeding and more durable context management:
interview, plan, test contract, explanation, handoff, bounded execution,
independent review, proof, and owner documentation.

## Repo Context

- Existing skills already enforce validation-first development and a strict
  quality loop.
- The deterministic AI4BINANCE core owns signals, risk, exchange checks,
  validation, and execution permission.
- Local LLM and agent outputs are advisory and loopback-only by default.

## Constraints

- Preserve Python 3.12.10 and repo-local `.venv` usage.
- Preserve `NO_TRADE`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` defaults.
- Do not read, print, copy, or commit secrets.
- Do not add an unattended executor. Background work must run only while the
  computer is on, the user session is active, and progress is inspectable.
- Keep factory artifacts reviewable text files and deterministic validators.

## Unknowns

- Exact model/provider for future execution handoffs.
- Whether proof videos should use browser automation, local TTS, or external
  services.
- How much autonomy the user will allow after the first review cycle.

## Recommendation

Start with the factory contract and skill suite. Add `BACKGROUND_SHIFT` only
after the contract proves useful on real tasks.
