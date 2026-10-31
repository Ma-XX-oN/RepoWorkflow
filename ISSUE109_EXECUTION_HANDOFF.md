# #109 Functional executor checkpoint — 2026-10-17

Status: **PARTIAL / NOT CERTIFIED** as of 2026-10-31. Do not merge or
publish stable tags. October 17 source pointers below are historical;
read the October 31 continuation at the end and
[ISSUE109_ACCEPTANCE_LEDGER.md](ISSUE109_ACCEPTANCE_LEDGER.md) first.
Exclusive implementation claim recorded on #109 in this session.

## Exact stacked source
- #84 accepted earlier: PR #672, source `b9acb02b15be3a9ccc0be10d4ffa1b56cfe8a398`
- #103: PR #679, source `101628e30879646aed9fcb0860f5db2e804cec11`, partial retirement preflight only
- #109: draft PR #680, initial functional executor checks and copied #677 admission modules. Source SHA must be read back from PR #680 on resumption.
- #677: draft PR #678, separate graph correction and branch-ref/discovery contract tests.

## Verified tests and scope
The exact GitHub source files were reviewed, and equivalent isolated
Python 3 code was compiled and exercised in a local temporary test harness.
**34 focused tests PASS** in the local harness, including provider-neutral
admission, immutable READY discovery, two-clone local Git publication,
retirement preflight and #109 guard negatives. This is **not** a claim
of complete repository regression or hosted CI for the PR head.

#109 now has a conservative boundary `execute_certified_done`:
1. re-read complete planner result and reject changed source/parent/intent;
2. require destination/ticket/SHA-bound `AdmissionDecision` (never bare True);
3. require a separate certified INT-ATTEMPT with immutable source PRELIM SHA;
4. supply exact candidate and expected-old destination SHA to provider;
5. treat missing provider response as UNKNOWN, never success;
6. independently request landed identity verification before returning accepted.

The callbacks are injected; **actual provider authority, authentication and
atomicity are not yet wired or demonstrated**. No production integration
occurred.

## Outstanding for #109 DONE
- Implement actual authoritative discovery, single-writer per-destination
  coordination, immutable submission registry, and safe restart/persistence.
- Prepare mutable INT-ATTEMPT against latest destination; only apply
  integration-specific changes; revalidate material/evidence/version changes.
- Wire #104/#542 exact gates and #119 provider adapter atomic merge with
  real provider readback and idempotent UNKNOWN reconciliation.
- Wire #103 cleanup once independently certified; protect unresolved cases.
- Complete ART/AIT/MIT/TIMEOUT/deferred queues, approved handoffs,
  atomic result history and source-to-landed evidence promotion.
- Verify production CLI wiring, all declared acceptance oracles (#583
  T01-T08, L08/L09/L10/L17/L18/L20), full regression and hosted CI.
- Resolve cross-PR branch assembly without duplicating or weakening #677
  parser and test coverage. Keep #85/#86/#676 security deferred.

## No unauthorized changes
No protected main ref, PR merge, provider ruleset or release tag changed.

## 2026-10-31 current continuation (supersedes source pointers above)

This file's October 17 exact-source pointers are historical. For current
source use the live branch `issue-109-accepted-assembly-20261030` and
`ISSUE109_ACCEPTANCE_LEDGER.md` on that branch. Do not promote old fixture or
hosted results to its current HEAD. The direct current `repo_workflow.py`
entrypoint calls `handle_public` without a trusted done executor; the
public command fails closed until an independently authenticated service is
bound. `done_runtime.execute_ready_done` still requires actual planner,
READY, provider, retirement, lifecycle and verification callbacks. Independent
release/MIT GitHub App issuer and stable shared lifecycle state authority
are not installed by historical test fixtures.

The #109 exact-source accepted product previously pinned by native workflows
is `59b4d62ef2c38a5cd53cfbe03f937c27aedcbc90`, not the current
consolidation HEAD. Native verification runs 41227150581 and 41227396552
had five successful jobs and an in-progress Windows full job when checked.
Historical three-OS read-only GitHub provider run 41222111102 succeeded, but
observed old main parent `f838ae7cddaa1376b086bb146a13bfec8602b085`;
it cannot certify an integration against newer main. Do not start redundant
native validation on ordinary pushes. The consolidated branch's native
workflow push triggers now use `.ci/run` exclusively; three historical
migration/certification workflows have separate, named path selectors. The
permanent guard `tests/test_ci_invocation_trigger_contract.py` is registered
under `.ci/tests.json` both here and on main.

Remaining: actual independently issued ART/AIT/release/MIT, trusted production
native executor connection, authoritative shared lifecycle state, current
parent/CAS acceptance, exact-current-source native suite, and independent
#583/#677 oracle readback. Preserve all existing ownership and security gates;
no production merge or stable tag is authorized by this checkpoint.
