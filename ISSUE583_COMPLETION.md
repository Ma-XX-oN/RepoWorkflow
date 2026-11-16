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
- [x] Verify the 14 historical partial cases against functional requirements.
- [x] Run lifecycle, CSV, graph, renderer binding and #109 workflow checks.
- [x] Record exact-source native platform results.
- [x] Publish the final evidence and completion handoff for #583.

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

## Exact-source execution evidence

Tested source: `62223b89eb4f1b78fb52f107190c76703c4282b0`, version
`0.1.122-issue.583.3.0`. It assembles #583 PR #666 source `c08d5260`,
#109 checkpoint `e1342a7b`, and accepted #660 `c5e258db` (verified ancestor).

| Environment | Result | Evidence |
| --- | --- | --- |
| Linux / Python 3.13 | PASS: 27 groups, 258 test executions and three platform probes, no failures/errors/skips | [run 43901040091, job 133417388248](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43901040091/job/133417388248) |
| Windows / Python 3.13 | PASS: same 27 groups, 258 test executions and three platform probes, no failures/errors/skips | [run 43901040091, job 133417388741](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43901040091/job/133417388741) |
| macOS 15 Intel / Python 3.13 | PASS: same 27 groups, 258 test executions and three platform probes, no failures/errors/skips | [run 43904346747, job 133429044958](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43904346747/job/133429044958) |
| Read-only GitHub provider-title merge | PASS: one real-provider test; lifecycle bytes unchanged | [run 43902175486](https://github.com/Ma-XX-oN/Disposable-001/actions/runs/43902175486) |

The selected regression covers lifecycle transitions/migration, independent clone
publication/recovery, CSV concurrency/freshness/merging, graph layout/accessibility,
renderer binding, version/source identity, functional PRELIM completion and manual
test catalogue/results/CLI. The three native probes cover graph rendering,
ticket merging and process argument limits. This is scoped functional regression,
not execution of unrelated legacy security/verifier suites.

## Corrected failures

- Original Windows recovery fixture could not remove read-only Git objects;
  TemporaryDirectory cleanup now removes the lost clone and asserts its absence.
- Native Windows clone checkout converted canonical CSV to CRLF; fixtures now
  commit `text eol=lf` Git attributes. Exact-byte assertions are preserved.
- The renderer manifest retained an older CSV blob. It now binds actual blob
  `3a1fe3fd40b0103365f332f3f54b10f9fc49e86e`; the other 17 material inputs
  remain unchanged. Native checks passed this binding on all three platforms.

Earlier failed run `43900388320` is historical and not passing evidence.
No production parent/main merge, stable tag or production deployment is claimed.

## Native runner availability

All three platforms' terminal logs were independently read back. The original
matrix run's aggregate result is failure because its macOS ARM64 job could not
acquire a runner; its Linux and Windows jobs both passed. Provider annotations
explicitly report ARM64 capacity constraints. The second queued ARM64 request
was cancelled. The supported `macos-15-intel` runner acquired a machine and
passed the identical source and checks in run `43904346747`.

These runner failures are not functional test failures and are not recorded
as passing macOS evidence. Only the completed Intel job supplies macOS PASS.

## Completion decision

The 14 historical partial cases are accepted under the corrected functional
scope and the retained independent lifecycle/CSV/graph oracle. No applicable
#583 acceptance item remains pending. External verifier programs and adversarial
certification are excluded, not outstanding work. #677 retains assembled-workflow
convergence ownership; #703 retains its separate independent MIT-provider scope.

The source branch and PR #666 are ready for review. Ticket completion does not
claim a protected-parent merge, stable release or production activation.
