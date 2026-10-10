# Issue #97 — Verified Minimum Hosted Test Architecture

Date: 2026-10-10.  Issue OPEN, draft PR #616 UNMERGED.
Canonical operational guide: ISSUE_97_LIVE_ACCEPTANCE_SETUP.md.

## Provider-backed facts

- PRIVATE sandbox Ma-XX-oN/Disposable-000 exists; owner admin rights
  confirmed.  Main, issue #1 and distinct source/target branches are
  initialized, and disposable PR #2 is CLOSED, UNMERGED.
- Authenticated private GitHub Actions provider probe confirmed
  total_count 0 for environments.
- The private repository's Rulesets API returned a plan-specific 403.
- Hosted shipped Python adapter denied four unauthorized mutations and
  failed closed on unsupported merge/check publication.  Independent
  before/after remote issue/PR/comment/ref state was unchanged.
- All positive authenticated adapter writes still require trusted #80
  standing-policy authorization; none have been executed yet.

## Evaluated execution architectures

| Option | Feasible | Additional authority |
| --- | --- | --- |
| RepoWorkflow-hosted GitHub runner | Yes | Cross-repo token |
| Hosted runner plus GitHub App | Yes | App identity/key |
| Dedicated self-hosted runner | Yes | Persistent runner |
| Sandbox-native hosted runner | SELECTED | Signed #80 grant |

The selected `ubuntu-latest` job uses only Disposable-000's native
job-scoped GITHUB_TOKEN, with Actions read, Contents write, Issues
write and Pull requests write, confined to that disposable repo.

A dedicated runner, private App key, PAT or persistent verifier
service is NOT demanded by the #80 contract.  No production
RepoWorkflow main, issue or release tag is changed.

## Private GitHub plan reality

Rulesets for private personal repositories need an eligible paid
plan.  GitHub Free/Pro/Team required deployment reviewers are
restricted to public repos.  A Pro upgrade alone would therefore
NOT implement the previous private environment-review plan.

Issue #97's disposable *test* need not acquire Enterprise or change
the sandbox to public.  Instead, an administrator independently
reviews the exact trusted workflow/candidate SHA and signs a
short-lived scoped #80 grant using a private OFFLINE Ed25519 key.
GitHub Actions repository variables controlled by the administrator
pin the issuer public key, issuer ID, exact grant ID, current signed
revocation state, exact trusted-main SHA and exact candidate SHA.
The GITHUB_TOKEN job cannot edit those Actions approval variables.

The grant and mirrored revocation document are signed.  The shipped
adapter invokes a separate verifier executable staged outside the
candidate checkout, and that verifier checks cryptographic signatures,
GitHub's authenticated actor, precise semantic capability, sandbox
issue and PR refs, grant lifetime, delegation and current revocation.
One-time grants and unverifiable claims always deny.

A cryptographic authorization decision is DISTINCT from GitHub
environment review and distinct from token possession.

## Security qualification

Without paid GitHub protection rules, a sandbox write token may also
have permission to modify sandbox main or reservation refs.  The
test adapter never intentionally uses those operations; the
independently reviewed exact candidate is mandatory.  Verifier
binary hash binding and the administrator-maintained signed
revocation variable detect unintended changes, but do NOT provide
hostile-code isolation from malicious candidate code holding the raw
sandbox token.  A separate credential-owning trusted broker would
be needed for that STRONGER production threat model.  Do not
misrepresent private Free as having active main/tag rulesets.

The isolated test's authorization validity is anchored in a
separately issued signed grant and current authoritative revocation
fact, not in a mutable local JSON file or PR author's claim.

## Executable artifacts

- `examples/issue-97-sandbox-hosted.workflow.yml`: sandbox hosted job.
- `examples/issue-97-verify-authority.py`: signed v1 verifier.
- `examples/issue-97-admin-sign-authority.py`: OFFLINE issuer utility
  for key generation, short-lived grant and revocation, no key uploads.
- `tests/test_repo_host_github_signed_verifier.py`: cryptographic
  positive/negative specification tests.
- `scripts/probe-repo-host-github-private-sandbox-deny.py`:
  authenticated real-provider six-operation fail-closed test.
- `scripts/probe-repo-host-github.py`: real authorized Python write,
  persisted outcome, replay/concurrency and cleanup acceptance.
- `ISSUE_97_LIVE_ACCEPTANCE_SETUP.md`: exact admin UI/CLI steps.

The sandbox already contains the hosted workflow and a trusted
verifier candidate; administrator-pinned issuer/grant variables
and signed grant issuance are NOT yet configured.
Do not mark DONE from mock GREEN or live negative results alone.
