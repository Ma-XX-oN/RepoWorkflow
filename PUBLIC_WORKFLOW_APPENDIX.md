# 14. Existing lower-level work — companion sections

Continued from [PUBLIC_WORKFLOW.md](PUBLIC_WORKFLOW.md).

## 14. Existing lower-level work

The revised public workflow reuses rather than discards existing lower-level
mechanisms where they still satisfy the new architecture:

- #5 — authoritative candidate bookkeeping and terminal tagging;
- #16 — validation evidence and reuse;
- #17 — prelim integration/reintegration/PRELIM tags;
- #18 — protected server enforcement;
- #19 — local Git guards;
- #27 — initialization.

Internal commands may remain temporarily for machine compatibility, but they
must not define the normal human-facing workflow or force GitHub-specific
semantics into the portable engine.

## 15. Remaining design work

The major unsettled details are tracked explicitly rather than hidden in this
synopsis:

- exact durable/shared versus clone-local `.repoworkflow/` schema (#57);
- multi-agent active-work representation (#57);
- synchronized ticket-state and direct-dependency representation (#57);
- authorization representation/lifetime (#56/#57);
- exact `done patch|minor|major` integration transitions (#56);
- test-evidence fingerprint/invalidation rules (#16);
- portable `repo-ci` adapter contract (#55).

These items must be documented and RED-tested before their production
implementation.
