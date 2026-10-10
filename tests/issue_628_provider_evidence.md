# Issue #628 — independent trigger acceptance evidence

Observation date: 2026-10-10 (Toronto).  Repository:
`Ma-XX-oN/RepoWorkflow`.  This ledger preserves actual provider
observations separately from mocks, static checks and local Git fixtures.

## Exact source / CI revision

- Source branch: `issue-628-trigger-probe-matrix-v3`.
- Verified source commit: `329067ffb9b9fa1cf0347cb5c2a7c0e2856a1479`.
- Self CI run: `38079318666`, run number 2246, SUCCESS.
- Issue tier: 16 marker-history cases, 20 observer cases, 12
  static-filter cases, 2 recorded-hosted-snapshot cases and 9 self-CI
  invariant cases.  All passed.
- Run: https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/38079318666
- Only `issue-validate` ran; platform integration and release jobs skipped.

## Real GitHub-hosted on-demand runs

Read-only GitHub Actions REST observations, cross-checked with GitHub
commit parents, committed `.ci/run` contents and plan-job logs:

| Run | Stage | Invocation SHA | Direct parent SHA | Actual tested SHA | Executed test jobs |
| --- | --- | --- | --- | --- | ---: |
| 37997910448 | temporary | ddbb99569f790944fed2fa3c8a431e02287e8da4 | 1cf52daea5405f28711c23fe7361a29ad6c079a6 | 1cf52daea5405f28711c23fe7361a29ad6c079a6 | 1 |
| 37998116102 | temporary | b5b61561940270e4cb01c0398d09e147123509b2 | e08bec458d18a89e87f86c552525868d5ddfa9a4 | 1cf52daea5405f28711c23fe7361a29ad6c079a6 | 1 |
| 37998546029 | regression | 1e7db817fbf633362f2e36bdc8ff7b66de735381 | a1632143f4b7ef4a0ea477e7dd508096a8d8336a | a1632143f4b7ef4a0ea477e7dd508096a8d8336a | 1 |
| 37999454160 | integration | 0c5cb0001b8ca8296ec479a687a0df5d118556b6 | 4a04dadff0a785e13e75ca89ba0bcf42fb412a4b | a1632143f4b7ef4a0ea477e7dd508096a8d8336a | 10 |

Every listed run concluded SUCCESS.  Each invocation commit had one parent
and changed only `.ci/run`.  The committed marker SHA exactly matched the
invocation commit's immediate parent.  For repeated requests the prior
tip included a canonical `testResults-541.jsonl` evidence publication
commit and/or an earlier marker.  The observed planner's `tested_sha`
correctly traced to the original source candidate rather than blindly
using the immediate parent.

Runs: https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/37997910448
https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/37998116102
https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/37998546029
https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/37999454160

Three earlier candidate workflow runs (`37890251614`,
`37890264970`, `37890670543`) concluded FAILURE and returned no jobs
in the job-list endpoint.  These are not successful execution evidence.

## Negative provider observations and limits

### Workflow-present source-only negatives

The #541 candidate workflow was present in the Git tree at all three
ordinary source/configuration commits below.  Each GitHub Actions REST
query `/actions/runs?head_sha=<SHA>` returned exactly one Self CI
pull-request run and **zero on-demand workflow runs** for that SHA:

| Source-only commit | Changed path | Self CI run | On-demand runs |
| --- | --- | ---: | ---: |
| `0059f626c7b35cb129310ca84f6ba006bc5d259e` | `tests/test_on_demand_workflow.py` | 37893404518 | 0 |
| `a1c8185e4008f9e573be27942f8874604046b09a` | `tests/test_hosted_result.py` | 37893227687 | 0 |
| `84f51585d962793c3286f7c360a89833adad32ca` | `.ci/tests.json` | 37893133837 | 0 |

These are real provider observations for ordinary changes on a branch
containing the candidate workflow.  They do not establish exclusion for
`main`, exact `prelim-main`, read-only `rwf test results --remote`,
or replayed webhook delivery.


- Queried all 203 recorded `main` branch GitHub Actions runs across
  three pages.  All were `.github/workflows/self-ci.yml` push runs.
  No on-demand run appeared among these historical records.
- `issue-628-trigger-probe-matrix-v3` produced Self CI pull-request runs
  only in the observed window; no on-demand workflow runs appeared there.
  The on-demand workflow is not present in this branch or default `main`.
  **Absence of an installed workflow does not certify event filtering.**
- Exact `prelim-main` returned zero historical Actions runs, so this is
  not a valid negative-path execution probe.
- #541 candidate workflow has `branches-ignore` entries for `main`
  and `prelim-main-*` but not exact `prelim-main`.  The branch-filter
  gate fails against that candidate.  Recorded on #541 in comment
  `6101127020`.
- The read-only observer `scripts/observe-ci-trigger.py` refuses to
  certify zero jobs unless the target workflow is registered and active,
  the observation window has ended, pagination is exhausted, and every
  selected run is terminal.  It validates committed request ancestry,
  retry evidence-hop history, duplicate invocations and actual test-job
  counts.  Its unit tests use mock provider responses; these are **not**
  substitutes for real negative provider observations.
- No workflow was installed, activated or merged by the #628 worker.

## Acceptance traceability

| Matrix case(s) | Evidence | Verdict |
| --- | --- | --- |
| T00 | Black-box Git fixture and observer zero-event tests | Fixture PASS; live exclusion pending |
| T01 | Git fixture plus four successful hosted invocations | PASS for dedicated request and SHA binding |
| T02 | Two successful temporary and regression/integration sequences | PASS for distinct invocation identities |
| T03 | Parser retry fixture and two real successive hosted requests | Retry chain PASS; missed-delivery recovery unobserved |
| T04 | Three live workflow-present source-only commits with zero on-demand runs | Provider PASS for sampled ordinary changes |
| T05-T06 | Git fixtures and static filter checks | Main and exact prelim-main active exclusions not certified |
| T07 | Read-only verifier fixture | Hosted read-only retrieval exclusion not observed |
| T08-T12 | Executable tamper, marker, SHA, mixed-source and ancestry tests | Black-box PASS; live rejection not observed |
| T13 | Two-request Git fixture | Multi-event delivery semantics not observed |
| T14 | Static #541 filter audit and GitHub run listing | FAIL: exact `prelim-main` missing |
| T15 | Duplicate-delivery observer rejection unit test | Mock PASS; live idempotency not observed |

**Closure gate:** #628 cannot be called DONE until the outstanding real
trigger exclusion/retry observations are established and the exact
`prelim-main` defect is corrected and verified.  These live tests are
not inferred from green static/mock CI.  The worker retains its V3 claim;
this evidence is a resumable integration handoff to #541, not a merge or
production workflow activation.
