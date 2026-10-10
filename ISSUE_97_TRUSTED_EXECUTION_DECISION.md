# Issue #97 — Functional GitHub Acceptance Boundary

Decision corrected 2026-10-10 under the owner's explicit instruction.
Issue #97 OPEN.  Draft PR #616 UNMERGED.  Direct blocker: #81 only.

## Distinguish contract from infrastructure

#81 requires a provider-neutral semantic adapter, authenticated and
authorized operations, fail-closed rejection, idempotency and actual
provider-backed acceptance of issue/PR creation and update.  Its
section 6 specifies explicit actor, scope, operation and expiry
verification at the mutation boundary.

#80 defines the canonical authorization evidence format.  #97 consumes
authorization decisions; neither #97 nor #81 requires a particular
offline certificate issuer, signing ceremony, permanent server,
protected-environment reviewer, paid GitHub plan, dedicated runner,
GitHub App or PAT.  No implementation of #85 is required before
#97 completes.

#85 owns enforcement of protected production main.  Ordinary #97
issue/PR mutations do not authorize merge or check publishing.

## Smallest approved live arrangement

The owner explicitly authorized a PRIVATE disposable repository:

https://github.com/Ma-XX-oN/Disposable-000

The repository already contains a designated issue, two distinct
non-main branches and a GitHub-hosted workflow.  Its separate
sandbox-main test authority implements the approved temporary
fixture scope, verifies authenticated `github-actions[bot]` through
GitHub GraphQL, matches issue/PR scope, run ID and expiry, and issues
strict #81 decision envelopes.  The shipped adapter uses its normal
authorization consumer, with the verifier staged OUTSIDE the
candidate's source checkout.

Use a native short-lived sandbox-only `GITHUB_TOKEN` on
`ubuntu-latest`, with only relevant Contents, Issues and PR write.
The job never modifies RepoWorkflow production main or release tags,
and all test PRs remain unmerged.

This is NOT production protected-main security enforcement and does
not purport to resist arbitrary unreviewed malicious candidate code
holding the disposable sandbox write token.  Such a threat model is
outside #97 and belongs to existing security ownership, including
#85.  Do not activate those tickets to certify the adapter.

## Real test results and exact blocker

- https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095457391

  Actual shipped Python issue update, comment, same-ID replay,
  changed-input refusal and competing comment processes executed.
  Independent GitHub readbacks verified one comment per request ID.
  The issue title was restored.  The run then failed on PR creation.

- https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095621430

  Actual shipped Python PR update PASS, including persisted state,
  fresh-process replay, same-ID conflict and stale-head refusal.
  Draft PR #2 was restored and closed without merge.

- https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095551998

  Native GitHub Actions `POST /pulls` conclusively returned HTTP 403:
  "GitHub Actions is not permitted to create or approve pull requests."

The one blocking administrative action is in Disposable-000 only:
Settings -> Actions -> General -> Workflow permissions -> enable
`Allow GitHub Actions to create and approve pull requests` -> Save.

The connected GitHub tools do not expose updating this setting.
No new GitHub issuer, admin-managed grant, offline certificate,
protected environment, self-hosted runner, ruleset, or broader
security deployment is required for these functional tests.

## Completion boundary

After PR creation is allowed, run the existing exact-source Python
probe through both real create and update, verify persisted PR
identity, request reservation records, replay and cleanup, then
run issue-level regression.  Only then may #97 report DONE and
close according to V3 rules.  Do not merge PR #616.
