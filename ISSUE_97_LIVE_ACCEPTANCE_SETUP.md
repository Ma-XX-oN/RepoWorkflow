# Issue #97 — Disposable-000 Functional Acceptance

Status: functional acceptance IN PROGRESS.  #97 directly depends on #81.
Existing V3 claim 6099480122; draft PR #616; NEVER MERGE.

## Binding issue-level contract

Authoritative #81: `REPOSITORY_HOST_MUTATION_CONTRACT.md`.

- Implement and test ordinary `issue.update`, `issue.comment`,
  `pull_request.create` and `pull_request.update`.
- Strict input/output, stale-head refusal, idempotent retry and
  unknown-outcome reconciliation remain mandatory.
- An actual unauthorized request must fail closed, per #81 section 6.
- No implicit PR close, merge or check publication.  The last two
  operations report `unsupported` while their independent owners'
  enforcement is unavailable.
- #80 owns authorisation EVIDENCE FORMAT, not a separately deployable
  online issuer prerequisite for completion of #97.
- #85 owns protected-main enforcement.  No rulesets, protected
  environment, offline signing ceremony, special runner or administrator
  grant are issue #97 completion prerequisites.

## Explicitly owner-authorized test scope

Private repository: https://github.com/Ma-XX-oN/Disposable-000

The owner explicitly authorized disposable issue/PR/branch mutations.
The separate sandbox-main test authority records this authorization as
a short-lived, scoped, outside-candidate executable.  It verifies the
actual GitHub Actions actor `github-actions[bot]`, run identity,
repository, operation, expiration and exact fixture scope.  It cannot
authorize changes to RepoWorkflow production main, production release
tags, arbitrary issues, PR merges or success checks.  The shipped
adapter's authorization consumer is NOT bypassed.

Sandbox fixtures:
- Issue #1: `RWF #97 SANDBOX live-mutation fixture`.
- Source: `refs/heads/rwf97-sandbox-source`,
  SHA `9bf44e1aaac2e49fe26949df3369c4fc10b462fc`.
- Target: `refs/heads/rwf97-sandbox-target`.
- Draft PR #2: separately created fixture for actual Python PR updates;
  restored and closed without merge.
- Temporary reservation tags and the two marked bot-authored issue
  comments remain as immutable provider evidence.

## Actual GitHub-hosted Python results

1. Run 38095457391:
   https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095457391

   The REAL shipped adapter updated issue #1, verified idempotent replay,
   added one uniquely marked comment, rejected changed same-ID content,
   and raced two independently launched Python comment mutations to one
   uniquely marked persisted comment.  It then attempted PR creation.
   PR creation failed at the GitHub provider with `unauthorized`.
   Finally, the issue title was restored.  The run is not an overall
   PASS; its completed stages have durable provider readback evidence.

2. Run 38095621430:
   https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095621430

   REAL shipped Python `pull_request.update` PASS on disposable PR #2:
   first write applied, fresh-process replay unchanged, changed same-ID
   request conflict, stale-head denial, exact remote readback.  PR #2
   was restored and closed without merge.

3. Run 38093785174:
   https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38093785174

   Six real Python operations without authorization correctly denied
   or declared unsupported.  Remote issue, comments, PR, branch SHAs
   and reservation tag state were identical before and after.

4. Run 38095551998:
   https://github.com/Ma-XX-oN/Disposable-000/actions/runs/38095551998

   Independent GitHub-hosted POST to the real PR-creation endpoint
   definitively returned HTTP 403:
   "GitHub Actions is not permitted to create or approve pull requests."
   This is an actual provider permission gate, not a #80 security
   infrastructure dependency.

## Only actual GitHub setting preventing positive PR creation

Open:
https://github.com/Ma-XX-oN/Disposable-000/settings/actions

Under **Workflow permissions**, enable:

  Allow GitHub Actions to create and approve pull requests

Then select **Save**.  Keep the repository PRIVATE and do not modify
RepoWorkflow or production protection rules.  No token, issuer
certificate, personal key, paid plan or privileged runner is needed.

This setting is necessary because #81's section 8 expressly requires
a REAL provider-backed PR creation, and the authenticated native
sandbox-token POST returned HTTP 403 before the write.  No connector
endpoint available in this ChatGPT session can change that Actions
administrative setting.

After enablement, the existing
`.github/workflows/rwf97-functional-acceptance.yml` in sandbox main
can be triggered by a new reviewed commit to that file.  It checks
the exact #97 candidate SHA and runs the shipped Python CLI end-to-end
using only the sandbox-native, short-lived `GITHUB_TOKEN`.
Do not run arbitrary unreviewed code with GitHub write credentials.

## Remaining actual acceptance after changing one setting

- Re-run functional probe to actual PR creation and update.
- Verify persisted exact PR head, title, draft, target and creator.
- Verify idempotent create/replay after restart, stale-head and
  same-ID conflicts, exact provider reservation hashes.
- Verify temporary PR close and issue restoration are complete.
- Run exact-head CI regression; record issue-level evidence.
- Close #97 only when every owned requirement is genuinely met.
- Do not merge PR #616.  Do not activate #85 or other deferred
  protected-main enforcement.

Optional offline-signed authority scripts added in an earlier design
are NOT acceptance prerequisites for #97 and should not be mistaken
for operational security deployment requirements.
