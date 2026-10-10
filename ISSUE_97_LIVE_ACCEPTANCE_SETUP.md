# Issue #97 — Protected Live-Mutation Acceptance Setup

Status: operator configuration required, not a DONE certificate.
Existing claim: 6099480122.  Existing draft PR: #616.  Never merge.

## Verified starting state (2026-10-10)

- RepoWorkflow is public, owned by a user account, not an organization.
- GitHub Actions registered the #97 live workflow on the issue branch.
- Hosted GET /environments with `actions: read` returned a valid listing
  with `total_count: 0`.  The `rwf97-sandbox` environment does NOT exist.
- The PR workflow token authenticated as `github-actions[bot]` but issue
  and PR creation attempts returned unauthorized.  The malformed tag-create
  request returned 422 and did not establish Contents-write authority.
- Actions administrative settings, repository variables and runner inventory
  were not readable by the token.  Do not treat those as configured.
- The #80 PR #614 delivers a contract and test matrix, NOT a deployed
  independently trusted verifier, issuer or standing policy.

## Required configuration — exact GitHub UI

1. RepoWorkflow -> Settings -> Environments -> New environment:
   name `rwf97-sandbox`.  Require a separate approved reviewer; enable
   Prevent self-review.  Select Custom deployment branches and allow ONLY
   `issue-97-github-host-mutation-adapter`, with no wildcard.
2. RepoWorkflow -> Settings -> Actions -> Runners:
   register an isolated, dedicated Linux runner with label
   `rwf97-trusted`.  Do not reuse a machine with production secrets.
   Install Python 3.13, GitHub CLI and the independent #80 verifier as
   a protected executable OUTSIDE the repository checkout.
3. Create/designate a disposable test repository OTHER than RepoWorkflow.
   Protect its default branch.  Create an open issue titled
   `RWF #97 SANDBOX <identifier>` and two branches
   `rwf97-sandbox-source` and `rwf97-sandbox-target`, based on
   different commits.  No production issues, branches or release tags.
4. In that sandbox's Settings -> Rules -> Rulesets, prevent editing and
   deleting `rwf-host-request-*` tag refs while allowing initial
   creation.  Verify the ruleset actually applies to the test credential.
5. Issue a short-lived token restricted to that sandbox, granting only
   Issues: write, Pull requests: write and Contents: write.  Prefer an
   installation token for an app installed ONLY on that sandbox.
   RepoWorkflow's own `GITHUB_TOKEN` cannot write a different repository.
6. RepoWorkflow -> Settings -> Environments -> rwf97-sandbox ->
   Environment secrets: store the sandbox token as
   `RWF97_SANDBOX_GH_TOKEN`.  Never put tokens in PR code or chat.
   Rotate or delete the token after the run.
7. RepoWorkflow -> Settings -> Secrets and variables -> Actions ->
   Variables: define all of the following:
   - `RWF97_ENABLE`: `true` only for an approved run;
   - `RWF97_APPROVED_SHA`: exact reviewed commit SHA;
   - `RWF97_SANDBOX_REPOSITORY`: sandbox owner/name;
   - `RWF97_SANDBOX_ISSUE`: marked issue number;
   - `RWF97_SANDBOX_SOURCE_REF`:
     `refs/heads/rwf97-sandbox-source`;
   - `RWF97_SANDBOX_TARGET_REF`:
     `refs/heads/rwf97-sandbox-target`;
   - `RWF97_AUTH_EXECUTABLE`: absolute trusted verifier path;
   - `RWF97_AUTH_SHA256`: lowercase SHA-256 of the reviewed verifier.

## Trusted authorization is separate from the GitHub token

The protected external verifier must be owned by a different OS
identity than the job runner, not writable by the runner, and installed
outside the PR checkout.  The job validates its administrator-pinned
SHA-256 before invoking it.  Keep issuer private keys and policy writes
in a separate protection domain that the runner cannot modify.

The protected external verifier must resolve the #80 grant against a
trusted issuer, authenticated actor, delegation, standing non-consuming
policy, capability, exact sandbox repository/issue/refs/candidate scope,
expiry, revocation and current policy revision.  It returns the canonical
#80 decision envelope, bound to the complete request digest.  A local
allow-all script, PR-shipped verifier or self-issued grant is NOT valid.
The adapter also checks the actor against GitHub's authenticated principal.
The verifier must be provisioned by an independently trusted operator.

## Execution without allowing a later code substitution

Prepare a local commit changing `scripts/issue-97-live-trigger.txt` on
`issue-97-github-host-mutation-adapter`.  DO NOT PUSH YET.  Review
the commit and capture `git rev-parse HEAD`; have the environment
administrator set `RWF97_APPROVED_SHA` to that exact SHA.  Then push
the already-reviewed commit.  GitHub Actions' push trigger filters on
the marker path, and the job rejects any other SHA.  An empty commit
will not satisfy the workflow's changed-path filter.

Approve the protected environment deployment independently.  The runner
first verifies the exact SHA, environment reviewers/branch restrictions,
sandbox identity and external trusted verifier.  Then the shipped Python
adapter executes through the GitHub CLI using the sandbox-only token.
The probe must independently read back the GitHub issue, comment, PR,
reservation tags and request digests; exercise changed-ID and stale-head
rejection, replay across fresh Python processes, and cleanup.  Record
actual GitHub API evidence and CI job ID; never equate mocks with live
provider mutation acceptance.

The existing probe does NOT yet establish every concurrency, revocation,
permission-denial and timeout/unknown-outcome acceptance case.  Extend
and certify those against the sandbox before #97 is marked DONE.

After execution, set `RWF97_ENABLE=false`, delete/rotate the token and
remove the dedicated runner's trust access as appropriate.  Keep immutable
reservation evidence and protected-default-branch rules intact.

## Safety boundaries

- Do not grant repository-wide write to normal pull-request workflows.
- Do not modify RepoWorkflow/main, production issues or release tags.
- Do not disable branch protection, reviewer checks or tag immutability.
- `pull_request.merge` and `check.publish` remain fail-closed; #542 and
  #85 own their separate downstream integration gates.
- If environment review, issuer, token scope or remote evidence cannot
  be independently established, leave the live tests pending and #97 OPEN.
