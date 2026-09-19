# 0004. Docker-First Environment

## Status
Accepted

## Context
Initially, SFLMS was planned as a locally-executed system with an
architecture designed to be "Docker-ready" for eventual migration —
environment variables were externalized from day one specifically to
make this transition low-friction. This was later superseded by an
explicit instruction: Docker is the **official** development and
deployment environment from day one, with no supported local execution
path at all. This is a genuine scope tightening, not merely a
formalization — Phase 1 code was in fact built and verified without
Docker before this decision was finalized (see `known-limitations.md`).

## Decision
Docker Compose is the only supported way to run SFLMS, in every
environment (development, local-server production, and any future
cloud deployment's underlying containers). No document in this
repository describes or endorses a non-Docker execution path.

## Consequences
- Every setup instruction (`onboarding.md`) assumes `docker compose`
  commands exclusively — no "if you prefer running locally" fallback
  exists anywhere in the documentation.
- The root `README.md`, written before this decision, is now stale and
  must be rewritten in Phase 2 (tracked explicitly in
  `known-limitations.md`, not silently left inconsistent).
- Removes "works on my machine" environment drift as a category of bug,
  at the cost of requiring Docker knowledge from every contributor.
- Positions the system for a low-friction future cloud migration
  (containers map directly to cloud orchestration units — see
  `system-architecture.md`).

## Alternatives Considered
- **Local execution as the primary path, Docker as an option**: this was
  the original design and is explicitly rejected by the superseding
  instruction — local execution is not merely de-prioritized, it is
  explicitly unsupported.

## Related
`decision-log.md` entry 4. `docker.md`. `onboarding.md`.
`known-limitations.md` (Phase 1's pre-Docker build, tracked as a gap).
