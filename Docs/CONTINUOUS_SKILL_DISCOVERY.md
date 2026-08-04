# Continuous Agent Skill Discovery

## ELI10

Bu belge dis dunyadan faydali ajan becerisi fikirlerinin nasil guvenli sekilde
incelenecegini anlatir. Sistem yeni bir seyi hemen kurmaz veya calistirmaz; once
karantinaya alir, puanlar ve insan incelemesi ister.


This workflow implements a quarantine-first version of the continuous learning
loop:

```text
Scout -> Filter -> Read -> Extract -> Score -> Generate -> Review -> Publish packet
```

It runs as research automation only. External repositories, shared skills,
marketplace items, copied prompts, and generated drafts are hostile input until
reviewed.

## Safety Boundary

The loop never installs, imports, executes, merges, pushes, or enables external
code. It cannot authorize trading, change risk limits, read secrets, or affect
live order gates.

Every report and draft preserves:

```text
RESEARCH_ONLY
HUMAN_REVIEW_REQUIRED
execution_allowed=false
installation_allowed=false
LIVE_ORDER_BLOCKED
```

## Outputs

- State: `State/skill-discovery.json`
- Audit ledger: `Logs/skill_discovery_events.jsonl`
- Quarantined drafts: `skill-staging/continuous-discovery/<skill-name>/`
- Library admission records:
  `skill-staging/continuous-discovery/_admit/<skill-name>/`
- Service logs: `Logs/services/skill-discovery.stdout.log`
- Service errors: `Logs/services/skill-discovery.stderr.log`
- Service health: `State/skill-discovery-health.json`

Each draft may include:

- `SKILL.md`
- `examples.md`
- `commands.md`
- `metadata.json`
- `review.md`

These files are review packets, not approved local Agent Skills.

Every candidate that is rejected or left outside the local skill library also
keeps an admission record:

- `admission.json`
- `not-admitted.md`
- `github-resolution.md`

The record stores why the skill was not admitted, credential-free GitHub search
queries for remediation evidence, and the required human approval marker:

```text
.çzüö
```

If that marker exists in the admission-record directory on a later cycle, the
record moves to `READY_FOR_LIBRARY_PR`. This still does not install the skill;
it only marks the packet as ready for a separate reviewed pull request.

## Commands

Run one cycle:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli skill-discovery-once --max-candidates 3 --format text
```

Run offline with a deterministic candidate file:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli skill-discovery-once --source-file .\Artifacts\skill-candidates.json --format text
```

Read the last state:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli skill-discovery-status --format text
```

Install the optional Windows startup task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Scripts\install_startup_task.ps1 -EnableSkillDiscoveryTask
```

The task runs while the Windows session is active and restarts according to the
existing startup task policy. It remains bounded by a single-instance lock.

## Review Rule

Publishing means producing a human-review packet. It does not mean installation.
A human reviewer must approve license, security, sandbox, provenance, ownership,
and AI4BINANCE authority boundaries before any draft can move toward a normal
repo-local skill review. Library admission additionally requires the `.çzüö`
marker and a separate PR.

