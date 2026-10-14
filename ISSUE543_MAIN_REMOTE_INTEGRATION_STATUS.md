# #543 — current-main development-branch remote testing integration

Status: INCOMPLETE / NOT MERGE READY.  Existing V3 claim: 6105182602.
Base main: cee5b34c2c83b5d05bf603192ec7f931569c2916.
Certified historical source: c9b58911a659d8ec8c133ff6015492d30762985a.
Latest untested source before this status update:
`0c814569d9d4ba30ba05fd8d78b9c52061b302de`.

## Scope reconciliation

- Historical PR #547 hosts on-demand five-stage execution and provider publication.
- Historical PR #552 owns the public six-family `rwf test` CLI.
- PR #567 provides historical assembled certification on its old target.
- All three diverge from current `main`.  Existing PRs and evidence are preserved.
- The integration branch is descended directly from the main SHA above.
- Preserve the existing main workflow/lifecycle code.  The new CLI is
  selectively merged into public_cli.py and public_commands.py.
- `.ci/tests.json` preserves all 20 main registrations and adds 62
  #540/#541/#542/#543/#545/#629 groups.  Ten historical unrelated
  #527-#550 lane/help registrations from the certified branch are
  intentionally not copied; their acceptance remains with their own issues.
- 72 distinct registered Python test modules were confirmed present by
  repository content lookup.  This is not execution evidence.

## New functional candidate

- New issue-branch-only workflow trigger: `.ci/run` path on `issue-*`.
  The planner rejects non-issue refs and invalid dedicated marker ancestry.
- Existing `self-ci.yml` is byte-identical to the current main copy.
- Five hosted stages call the unified public runner.  The workflow separates
  read-only execution, write-scoped publication, and independent read-only
  remote result retrieval.
- Immutable result artifact publishing, canonical per-issue JSONL,
  invocation/source identity checks, and retry lineage code are staged.
- Regression tests have been updated for the new workflow scope and
  publisher/read-only result separation.
- The initial tracked `.ci/run` is blank and inert.  No request was made.

## Acceptance ledger

| Gate | Method / exact revision | Result |
| --- | --- | --- |
| Parent current-main ancestry | GitHub compare, base cee5b34c | PASS static |
| PR 547/552/567 source audit | GitHub issue and diff inspection | PASS audit |
| Source/test registration presence | GitHub file lookup, 72 modules | PASS static |
| Self CI preserved | Exact Git blob SHA comparison with main | PASS static |
| Issue branch trigger scope | Read on-demand-ci.yml | PASS static |
| Runtime CLI and syntax | Not executed for new candidate | INCOMPLETE |
| Self CI on new candidate | No new PR run or check returned | INCOMPLETE |
| Real request / hosted 5-stage runs | Remote marker write blocked by tool safety | INCOMPLETE |
| Immutable new-provider artifact | No new hosted run | INCOMPLETE |
| Read-only retrieval and retry | No new hosted run | INCOMPLETE |
| Forgery/stale-parent/negative provider cases | No new hosted run | INCOMPLETE |
| Exact-candidate full regression/integration/platform | No new hosted run | INCOMPLETE |
| Protected production release | Owned by #85 / #86 | SECURITY-DEFERRED |

The GitHub write interface rejected a dedicated `.ci/run` request and
also rejected creation of the intended draft pull request.  Never interpret
the previously certified branch's PASS evidence as proving this new source.


## Integration defects corrected after initial staging

- Reconciled provider verification with the new workflow name, four required
  jobs (plan, validate, publisher, results), exact workflow path/ref and
  event-branch identity.  A valid old staging result does not automatically
  certify this new branch.
- The independent publisher now downloads its staged log to
  `.repoworkflow/validation/`, not the repository root.
- Evidence transfer must succeed before the write-scoped publisher becomes
  eligible; the public readback runs in a separate read-only job.
- Added/adjusted negative fixtures for workflow identity, forged branch,
  failed/missing publication and readback jobs, and canonical artifact path.
- Reconciled legacy public validation documentation while preserving the
  separately required manual-integration acceptance boundary.
- Retained prior PRs and #629's independent test harness.  No historical
  results were reclassified as exact-candidate acceptance.

## Independent source-level contract checks

Twelve of twelve GitHub-content static checks passed at the source revision
preceding this status update: issue-branch/marker-only trigger, no release job,
five public stage entrypoints, read-only runner, publisher-only write scope,
canonical download, successful transfer gating, read-only results job,
single-parent marker ancestry, provider workflow/branch attestation,
atomic publisher remote-tip comparison, and results retrieval without new
test dispatch.  The registered 72 Python module paths were also individually
confirmed present; this does not establish runtime import or test success.

The Self CI workflow is byte-identical to current main.  Its **existing**
`release` job has a main-push stable-tag path.  Do not merge this candidate
without explicit authorization and review of that release boundary; the
existing workflow was deliberately not modified as part of #543.

**New-candidate runtime tests: NOT RUN.**  GitHub reports no Self CI or hosted
workflow run/check on this new branch candidate.  The direct GitHub marker
write and draft PR creation were rejected by service safety checks.  The
container cannot reach the GitHub hostname, and the connected GitHub tools
provide no workflow-dispatch action.  The provider evidence and negative
request/retry matrix remain INCOMPLETE.

## Integration / closure order

1. Obtain an authorised GitHub Actions trigger and open a draft PR from this
   branch to `main`; inspect exact main tip again before merge preparation.
2. Run shipped public CLI, syntax, new workflow contract, source-size, Self CI,
   regression and integration on the exact new candidate.
3. Execute real provider requests for all five stages, retry, invalid
   marker/ref, stale lineage, failed/incomplete evidence and cache invalidation.
4. Verify immutable provider artifacts, write-scoped publication and
   independent read-only remote results retrieval against each exact SHA.
5. Reconcile any new main changes and repeat invalidated checks.
6. Record candidate, provider artifacts, PASS/FAIL by criterion, and obtain
   explicit merge authorization.  Only after inclusion is verified, reconcile
   closure of superseded PRs #547/#552/#567 while preserving their evidence.
7. Keep #85 SECURITY-DEFERRED; #86 retains protected stable release.
