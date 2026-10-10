# Per-unit validation coverage and applicability (#95)

Status: pure semantic coverage evaluator contract for successor #69.

## Definitions

The requested catalogue expands all subsets, groups, fast profiles and
complete gates into sets of atomic test-unit requirements.
A Requirement carries unit ID, expected #68 input fingerprint and required
mode (automated or manual).

An Evidence record carries a unit ID, observed #68 fingerprint, verdict
(PASS, FAIL, INCOMPLETE or PENDING), execution mode and provenance identifier.
Authenticity, immutable audit identity, exact candidate and valid dependency
closure must be verified before admitting a record to this pure evaluator.
#69 owns storage and #70 owns local-to-hosted import trust.

Per required unit the evaluator returns:

- satisfied: matching, applicable PASS evidence.
- pending: matching, applicable PENDING evidence without a PASS.
- stale: evidence exists, but none matches fingerprint and required mode.
- missing: no applicable PASS/PENDING; includes current FAIL/INCOMPLETE.

Coverage is complete only if every required atomic unit is satisfied.
Duplicate required IDs, malformed SHA-256, unknown modes/verdicts and invalid
record types fail closed.

## Invariants

Command names and broad-run success are never coverage evidence. A broad
execution contributes only the actual recorded test units. Narrow runs can
collectively cover full ART/AIT. Fast alone never implies full ART.
Matching automated PASS cannot satisfy manual/MIT requirements.
Changed relevant inputs stale affected units while unchanged independent
units remain satisfied. Execution location does not determine identity.

Among matching observations PASS has precedence, followed by PENDING;
FAIL/INCOMPLETE never satisfy. Invalidated or untrusted evidence must be
excluded before evaluation. These pure rules do not override authenticity,
provenance or supersession policies.

## Downstream

#69 stores immutable history and exact candidate/provenance in coordination
with #57. #70 authenticates local or hosted evidence for reuse. #110
schedules only missing automated work, never manufactures MIT evidence.

Tests: tests/test_validation_coverage.py and Self CI verification group
issue-95-coverage-applicability.
