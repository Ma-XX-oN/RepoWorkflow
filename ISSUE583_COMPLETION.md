# Issue 583 functional certification

## Governing requirements

- Preserve the independent 74-case lifecycle/CSV/graph acceptance oracle.
- Apply the approved single-PRELIM and Q/R version workflow from #109.
- Exclude external authorization/evidence verifier programs from certification.
- Exclude adversarial investigation, implementation and certification entirely.
- Keep ordinary candidate matching, stale-result refusal, concurrency, recovery,
  durable history, CSV migration and graph CLI requirements.
- Verify the assembled source on Linux, macOS and Windows.
- Preserve historical evidence without treating superseded gates as blockers.

## Completion checklist

- [x] Assemble #583 PR #666 with completed #109, retaining #660 fixes.
- [x] Reconcile the certification scope in SIX_STATE_ACCEPTANCE_MATRIX.md.
- [ ] Verify the 14 historical partial cases against functional requirements.
- [ ] Run lifecycle, CSV, graph, renderer binding and #109 workflow checks.
- [ ] Record exact-source native platform results.
- [ ] Publish the final evidence and close #583.

The original ledgers remain historical records. This document and the revised
matrix govern final functional acceptance. Security certification is not pending.

## Reconciliation of the 14 historical partial cases

| Cases | Applicable functional criterion | Verification |
| --- | --- | --- |
| T01–T08 | Eight legal transitions and 34 rejected state/action pairs; persistent readback | `tests.test_lifecycle_store` independent transition cross-product |
| L08 | Four-step lifecycle with candidate and history preserved | Lifecycle round-trip and `tests.test_done_workflow` actual Git completion |
| L09 | Rejection/resubmission retains history and uses the new candidate | `test_rejection_and_resubmit_retains_old_candidate_history` |
| L10 | Changed candidate requires reopen/review/revalidation | `test_accepted_changed_candidate_requires_reopen_new_review`; #109 parent reconstruction checks |
| L17 | Missing/mismatched candidate leaves lifecycle unchanged | `test_review_candidate_cannot_change_at_acceptance_or_completion` |
| L18 | Stale candidate/parent/results cannot complete; current results can | `tests.test_done_workflow` parent-advance, failed-test and missing-platform checks |
| L20 | Run declared automated checks; require manual verdicts only when declared | `tests.test_done_workflow` real catalogue execution with and without manual cases |

These criteria do not require an external authorization/evidence executable,
production issuer deployment, attack simulation or exhaustive forgery testing.
The original provider-title and shared-GitHub concurrency evidence is retained
in the historical crosswalk. Current native results must identify their own
source and scope; historical provider runs are not relabelled as fresh runs.
