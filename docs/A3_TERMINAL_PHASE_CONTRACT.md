# A3 terminal-phase contract and A4 integration handoff

Scope: #571, a pure phase-transition planner.  A4 (#572) exclusively
integrates Git, the public test CLI, canonical evidence and hosted workflows.

## Authority and identity

- The repository version adapter defines
  `X.Y.Z-issue.N.Q.R`, starting with Q=0, R=1.
- Regression failure requests `task --increment CI-iteration`, increasing
  R only for the next attempt.  Regression PASS does not increment R.
- Failed integration requests `task --increment merge-integration-failed`,
  increasing Q and restarting R=1 for the next generation.
- Integration PASS does **not** increment R.
- #17 defines the immutable candidate namespace
  `vX.Y.Z-PRELIM-N.Q.R`.  It must never be mistaken for stable `vX.Y.Z`.
- `-CI-FAIL` is the existing terminal FAIL suffix in terminal_tag.py;
  the user explicitly confirmed that **all version tags** may carry
  `-CI-FAIL` when CI reports failure, including PRELIM integration tags.
  This resolves the former naming ambiguity; A4 must still require
  authoritative failure evidence before publication.
- INCOMPLETE produces no version or tag consumption in either phase.

## Transition matrix

| Phase | Outcome | Tag | Next version |
| --- | --- | --- | --- |
| regression | PASS | `vX.Y.Z-issue.N.Q.R` | unchanged |
| regression | FAIL | `vX.Y.Z-issue.N.Q.R-CI-FAIL` | R+1 |
| regression | INCOMPLETE | none | unchanged |
| integration | PASS | `vX.Y.Z-PRELIM-N.Q.R` | unchanged |
| integration | FAIL | proposed `vX.Y.Z-PRELIM-N.Q.R-CI-FAIL` | Q+1, R=1 |
| integration | INCOMPLETE | none | unchanged |

For a given exact phase/version/candidate, a terminal result is immutable.
Repeating an identical result is idempotent.  A contradictory PASS/FAIL, or
INCOMPLETE after a terminal result, is rejected.  A prior INCOMPLETE may
later become PASS or FAIL without consuming a new version.

## A4 acceptance

A4 must read existing immutable local and remote tags and authoritative
per-issue JSONL before supplying `prior_terminal`; the planner itself never
trusts an unverified source and makes no persistence claim.  Assert original
candidate SHA (not a later `.ci/run` commit), annotated immutable refs,
remote equality or collision refusal, missing/invalid evidence rejection,
concurrent attempts, and no stable tag before protected server main.
Run the full regression and platform/provider integration matrix; issue
tests by themselves are not a live publication certification.

The executable `tests.test_phase_terminal` suite covers the decision
matrix, full failure/retry/pass lifecycle, idempotency and opposite-result
rejection, incomplete-to-PASS retry and invalid input boundaries.
