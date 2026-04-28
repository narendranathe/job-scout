# AGENTS.md

## Required Read Order

1. `README.md` — user-facing behavior, usage, and contribution flow.
2. `specs/README.md` — engineering context: constraints, progress, decisions, failures, and next work.
3. `UBIQUITOUS_LANGUAGE.md` (if present) — canonical terminology.

## Execution Rules

- Keep `README.md` understandable to users and contributors.
- Keep `specs/README.md` current before compacting context and at session end.
- Work from `## Open Issues and Next Work` in `specs/README.md`.
- Record major trade-offs and reversals under `## Design Decisions` and `## What Failed or Was Reverted`.

## Handoff Contract

When ending a session, update `specs/README.md` so the next agent can continue without rediscovery.
