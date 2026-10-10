# Issue #97 — Minimum Trusted Live Acceptance Architecture

Status: NOT DONE.  Claim 6099480122, draft PR #616; never merge.

## Decision (2026-10-10)

Preferred: a GitHub-hosted Ubuntu runner in a disposable *sandbox*
repository, invoked by a protected `workflow_dispatch` on sandbox
`main`.  The job's own short-lived `GITHUB_TOKEN` has only
`contents: write`, `issues: write`, and `pull-requests: write`
within that sandbox.  No self-hosted runner, PAT or separately
registered GitHub App is needed for this preferred path.  This
requires actual provider write acceptance before we claim success.

Workflow template:
`examples/issue-97-sandbox-hosted.workflow.yml`.
Trusted environment check template:
`examples/issue-97-sandbox-verify-environment.py`.

The prior `.github/workflows/issue-97-live-mutation.yml` remains an
OPTIONAL alternative.  It uses a separate sandbox credential and
trusted runner, but those are NOT architectural prerequisites.
Do not provision them just to use the preferred sandbox-native path.

## Verified facts versus assumptions

- GitHub Actions in RepoWorkflow reported zero environments through
  authenticated GET /environments with actions:read.  No protected
  `rwf97-sandbox` environment currently exists in RepoWorkflow.
  This says nothing about a future disposable sandbox repository.
- The ordinary read-scoped PR token denied issue/PR create attempts.
  It does NOT disprove a specifically approved sandbox job's
  Issues/Pull requests/Contents write permissions.
- The #80 source PR #614 supplies only the semantic authorization
  contract and acceptance matrix.  No operational trusted issuer,
  standing grant, revocation service or verifier was established.
- A GitHub-hosted runner can execute Python and GitHub CLI.  A
  separately registered self-hosted runner is not necessary.
- A sandbox-owned GITHUB_TOKEN is repository-scoped; the template
  never grants write access to RepoWorkflow/main or its real issues.

## Exact GitHub UI procedure — minimal preferred path

1. Use a NEW disposable GitHub repository, for example
   `Ma-XX-oN/rwf97-acceptance-sandbox`.  Do not use RepoWorkflow,
   an existing working repository or an unrelated testing project.
   Set its default branch to `main`.  Ensure Actions is enabled.
2. Open sandbox -> Settings -> Rules -> Rulesets and protect `main`.
   Reject force pushes and deletion; require independent review for
   changes to the trusted workflow, verifier, policy and fixtures.
   Protect `rwf-host-request-*` tags against update/deletion while
   allowing their initial creation.  Verify rules apply to the
   GITHUB_TOKEN installation principal, not only human writers.
3. Open sandbox -> Settings -> Environments -> New environment.
   Name it `rwf97-acceptance`.  Require an independent reviewer and
   Prevent self-review.  Restrict deployments to exactly `main`.
   Disable administrative bypass if the plan permits it.
4. On the sandbox's protected `main`, install the reviewed files:
   - `.github/workflows/issue-97-sandbox-acceptance.yml`, copied
     from `examples/issue-97-sandbox-hosted.workflow.yml`;
   - `trusted/rwf97/verify-environment.py`, copied from
     `examples/issue-97-sandbox-verify-environment.py`;
   - `trusted/rwf97/verify-authority`, an independently reviewed
     and functioning #80 authorization verifier.  Its code and grant
     issuer must be independent of the untrusted #97 PR checkout.
5. Add a marked sandbox issue titled `RWF #97 SANDBOX <identifier>`
   and two separate branch refs `rwf97-sandbox-source` and
   `rwf97-sandbox-target` with distinct commits.  Neither may be
   the default branch.  No production release tag may be targeted.
6. Sandbox -> Settings -> Secrets and variables -> Actions ->
   Variables: set:
   - `RWF97_ENABLE=true` only during the approved test;
   - `RWF97_APPROVED_SHA` to the EXACT independently reviewed #616
     commit (40 lowercase hex characters);
   - `RWF97_VERIFIER_SHA256` to the pinned SHA-256 of the trusted
     verifier file as installed on sandbox main;
   - `RWF97_SANDBOX_ISSUE` to the disposable issue number;
   - `RWF97_SANDBOX_SOURCE_REF` to
     `refs/heads/rwf97-sandbox-source`;
   - `RWF97_SANDBOX_TARGET_REF` to
     `refs/heads/rwf97-sandbox-target`.
   No App key, PAT or cross-repo token secret is required.
7. Sandbox -> Actions -> Issue 97 sandbox-hosted Python adapter
   acceptance -> Run workflow, choose protected `main`, and obtain
   independent environment approval.  The job fetches the public #97
   branch without credentials and rejects a different exact SHA.

The sandbox's protected workflow must remain on a trusted main SHA,
distinct from the candidate branch under test.  Do not checkout PR
workflow YAML into the privileged job.  Do not give the candidate a
GitHub token for RepoWorkflow itself.

## Independently authorized #80 verifier — not an approval shortcut

Environment review authenticates the deployment approval, NOT the #80
grant.  A trusted verifier needs an independently authenticated issuer
and delegation, a verified actor (the GitHub App installation actor),
canonical requested capability and exact sandbox scope, grant
`not_before`/`expires_at`, live revocation and policy revisions,
and a validated binding to the complete request digest.

The verifier must reject caller-supplied unsigned grants, missing or
unavailable policy/revocation, incorrect scope/issuer/actor, expired
authentication, changed inputs and unsupported consumption semantics.
#97's existing adapter only consumes independently verified,
non-consuming standing-policy decisions.  A one-time grant requires
separate atomic consumption; it must NOT be silently promoted to a
standing policy.  The verifier must recheck current authoritative
state on EACH protected request, including restart/retry.

The sandbox's protected `trusted/rwf97/verify-authority` is
installation material, not an authorization record by itself.
An issuer must independently issue and authenticate a scoped standing
policy with authoritative revision/revocation proof.  No working
verifier or issuer has yet been found in #80 or in connected tooling.
The setup is not complete until its positive AND negative decisions
pass independent tests.  Do not install an allow-all verifier.

## Provider-backed acceptance and teardown

The template's job runs the actual shipped Python adapter through
`scripts/probe-repo-host-github.py`.  It checks GitHub's persisted
issue/PR state, unique comment marker/body, request tag/commit digest,
idempotent replay from fresh processes, changed-ID conflict,
simultaneous requests, rejected unsupported merge/check, and cleanup.
It never targets RepoWorkflow/main or a production issue.

Before issue DONE, separately execute and record the remaining live
authorization negatives: missing/wrong/expired/revoked standing policy,
permission rejection, changed scope, concurrent revocation, provider
unknown-outcome and recovery.  Do not treat a mocked negative as a
real-provider authorization result.  Ensure the sandbox's default
branch and reservation-ref protection rules were actually enforced.

After testing: sandbox -> Settings -> Secrets and variables ->
Actions -> Variables: set `RWF97_ENABLE=false`.  Preserve audit
records; close the disposable PR and restore the issue title.  The
sandbox may then be archived or deleted by its owner after evidence
retention.

## Alternative architectures (not required for preferred path)

A GitHub-hosted RepoWorkflow job with a protected environment can
use a sandbox-scoped credential to reach a different repository.
A GitHub App installation token requires an app identity/private key
and creates more configuration than the sandbox-owned GITHUB_TOKEN.
A fine-grained sandbox PAT also adds an expiring secret.  Both avoid
a dedicated runner but are unnecessary when the approved workflow
runs *inside the sandbox repository*.

A dedicated self-hosted runner is needed only for a separately
required on-premises issuer/HSM, private network or native hardware
that GitHub-hosted runners cannot access.  None is established by #80
or by the existing provider probes.  Hosted execution still needs a
trusted verifier and independently issued grant; no runner changes that.
