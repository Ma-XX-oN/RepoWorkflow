# #543 — current-main development-branch remote testing integration

Status: INCOMPLETE / NOT MERGE READY.  Existing V3 claim: 6105182602.
Base main: cee5b34c2c83b5d05bf603192ec7f931569c2916.
Certified historical source: c9b58911a659d8ec8c133ff6015492d30762985a.
New untested source before this handoff note: e6145f86f31310d30fe6b26371e6e88ca400888f.

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
