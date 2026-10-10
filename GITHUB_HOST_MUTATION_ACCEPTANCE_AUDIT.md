# Issue #97 — GitHub Mutation Adapter Acceptance Audit

Status: OPEN until real-provider acceptance is recorded.  This is not a DONE
certificate.  The #97 prerequisite is #81; #85 and #542 are NOT prerequisites.

## Frozen input contracts

- #81: REPOSITORY_HOST_MUTATION_CONTRACT.md, PR #605, commit
  1241bcec7802a753f6ab3db43c335bba9f802fbc.
- #80: AUTHORIZATION_EVIDENCE_CONTRACT.md, PR #614, commit
  fdc3ee15b03173d6d2fbbd2bd71abf7314e3ca2e.
- Branch: issue-97-github-host-mutation-adapter; draft PR #616.
- Neither contract was merged or bypassed by this adapter.

## Implemented mutation behaviour

- `adapters/repo-host-github.py`: bounded strict JSON stdin protocol;
  exact request identity, semantic parameters and structured result/error.
- `repo_host_github_authority.py`: independently configured absolute-path
  verifier; exact request scope and actor proof bound to authenticated
  GitHub token principal; deny when verifier is missing or untrusted.
  Only verified non-consuming standing grants are presently accepted;
  one-time grant consumption remains fail-closed.
- `repo_host_github_provider.py`: authenticated GitHub REST/GraphQL
  primitives, provider error classes, unique immutable tag reservation
  per repository/operation/request ID and persisted request digest.
- `repo_host_github_mutations.py`: issue.update, issue.comment,
  pull_request.create and pull_request.update; exact ref/head checks,
  result normalization, retry reconciliation and unknown-outcome refusal.
  PR draft conversion uses GitHub GraphQL rather than unsupported REST PATCH.
- `repo_host_github_reads.py`: normalized provider identity reads.
- `pull_request.merge`: explicitly unsupported without atomic server-side
  destination-tip enforcement and remote-finalizer authority.
- `check.publish`: explicitly unsupported without authenticated evidence
  and authorized required-context publication.
- `capabilities`: advertises the four ordinary mutations only when a
  verifier executable is configured.  Never treats capability as a grant.

## Additional independent negative acceptance

- PR creation now checks the source branch, source repository and head SHA
  together, rejecting other branches or fork repositories even when commit
  objects are identical.  On a newly created PR, the adapter also confirms
  the provider persisted the exact requested title.
- Tests exercise same-SHA foreign branch replay, same-SHA foreign repository
  replay, mismatched provider source after creation, and missing title write.
- These are mock-provider regression tests, not live adapter certification.

## Cross-platform executable evidence (2026-10-10)

- Dedicated least-privilege GitHub Actions workflow:
  `.github/workflows/issue-97-platform-acceptance.yml`.
- Exact head: `79a21795909aac074b6dd0ac4dd9ee2fac1b1890`.
- Run: https://github.com/Ma-XX-oN/RepoWorkflow/actions/runs/38081833496
- Ubuntu, Windows and macOS: each completed SUCCESS with 57 tests,
  exercising subprocess CLI behaviour, authorization decisions against
  fakes, four provider mutation paths, reads, reservations and errors.
- An initial Windows failure resulted from a POSIX-only absolute verifier
  path in a test fixture.  Corrected the fixture to use a runner-native
  absolute path, then reran all three platforms to GREEN.
- The workflow has `contents: read`, no checkout-persisted credentials,
  and explicitly empties GitHub authentication variables; it cannot mutate
  hosted repositories.  Mock/provider-neutral execution is not live
  authenticated Python-adapter certification.

## #80 and available credential mechanism

- Closed #80 published PR #614 at
  `fdc3ee15b03173d6d2fbbd2bd71abf7314e3ca2e`.
- That handoff consists of the authorization evidence semantic contract and
  acceptance matrix; it does not install an executable trusted verifier,
  provision authorization issuer records or activate remote enforcement.
- Connected GitHub tools authenticate provider actions and support issue
  comments/changes, PR metadata and repository file commits.  Their
  credentials are kept inside the connector and are not exported to a local
  subprocess or GitHub CLI.  Thus provider smoke tests are meaningful but
  cannot run the shipped `adapters/repo-host-github.py` path.
- Live ordinary operations need both independently validated #80 standing
  authorization through `RWF_REPO_HOST_AUTH_COMMAND`, plus a GitHub CLI
  authentication source with Issues/Pull requests write and Contents write
  for durable reservation refs on an approved sandbox repository.
- Production finalization remains denied: the provider's merge endpoint has
  no required destination-tip atomic predicate, and check publishing lacks
  independent authenticated evidence authority.  These are not prerequisites
  of the four ordinary mutation paths and must never be reported as passed.

## Smallest safe external enablement

Use an approved isolated sandbox with a protected trusted verifier deployed
outside the unreviewed PR checkout and independently issued non-consuming
standing-policy authorization.  Supply a repository-scoped GitHub App
installation token or equally scoped ephemeral credential **through a trusted
runner/environment or local secret store**, never in comments/chat and never
to untrusted pull-request jobs.  Run
`scripts/probe-repo-host-github.py` in that protected environment with a
disposable issue and two non-main source/target branches.  Retain immutable
GitHub request tags and the exact commit/run evidence.  The user only needs
to approve/provision that protected test environment if it is not already
available; no secret values belong in the conversation.

## V3 authenticated Actions investigation and hardened handoff

- Inspected all relevant current workflows.  Self CI uses read-only
  contents except for its release job on `main`; the existing native
  dependency migration workflow requests `issues: write` only on its
  dedicated migration branch.  No production workflow grants all three
  adapter mutation permissions as a combined trusted test capability.
- The linked GitHub account has repository administrator access.  That
  is NOT evidence of a GitHub Actions job token's write authority.
- The existing #97 workflow explicitly requests read permissions.
  Real Python `GitHubBackend` calls succeeded with the hosted
  `GH_TOKEN: github.token` installation credential.  An invalid
  issue-create POST (missing required title) was rejected with an
  `unauthorized` provider error.  This demonstrates issue-write
  refusal for the currently read-scoped job without creating an issue.
- Installation token `GET /user` failed.  Live GraphQL
  `query { viewer { login } }` returned `github-actions[bot]`.
  The adapter now uses that verified provider identity fallback only
  when REST user lookup was unauthorized.  A null, malformed, or
  denied GraphQL viewer never becomes actor authority.
- #80 PR #614 contains two contract/matrix documents; no runtime
  trusted verifier, independent policy issuer or standing grant is
  present in that handoff.  Production actor, issuer, delegation,
  current revocation and scope cannot be invented in this adapter.
- The verifier consumer refuses relative paths, PR-workspace
  executables and argument-injected interpreter commands.  Its
  deployment contract requires one independently protected absolute
  executable outside the checkout; a file in this PR is NOT authority.
- The live probe now refuses production RepoWorkflow, requires two
  `rwf97-sandbox-` branch refs and a marked disposable sandbox issue,
  requires distinct source/destination SHAs, independently reads back
  persisted issue/PR state and records PASS only after cleanup.
- Credential-independent tests cover unauthorized operations, strict
  parser errors, persistence/retry logic via provider doubles,
  concurrent reservation races, failed cleanup, protected workflow
  configuration, and exact candidate identities.
- Dedicated optional `.github/workflows/issue-97-live-mutation.yml`
  is committed on the same #97 branch, without authorizing a merge.
  It has read-only native token permissions; execution requires the
  separately set `RWF97_ENABLE=true` repository variable, a protected
  `rwf97-sandbox` environment, a trusted `rwf97-trusted` runner,
  a sandbox-only installation credential in environment secrets,
  external trusted verifier and marked sandbox fixture variables.
  If these are absent, mutation acceptance has not been performed.
- GitHub Actions native `GITHUB_TOKEN` is scoped to the workflow
  repository, so a token from RepoWorkflow cannot grant mutation
  rights in a different dedicated sandbox repository.  The sandbox
  credential must be independently scoped to that sandbox; no token
  value is placed into source code, issue comments, logs or chat.
- No repository or organization security configuration was changed.
  Connector tools do not expose installed environment secret contents,
  approval/ruleset settings or a means to deploy the verifier.
  Treat those settings as UNVERIFIED, not as configured or absent.

### Minimum remaining externally authorized setup

A security/workflow operator must designate an isolated sandbox
repository (or create one), configure an approved protected environment
with trusted runner label `rwf97-trusted`, deploy a real #80-compatible
verifier outside the PR checkout with authenticated issuer/actor and
current scope/expiry/revocation evidence, and configure a sandbox-only
GitHub App token via `RWF97_SANDBOX_GH_TOKEN` environment secret
(Issues write, Pull requests write, Contents write for reservation refs).
Set the four sandbox fixture variables and explicitly enable
`RWF97_ENABLE` only after approval.  A push of the dedicated live
workflow trigger marker can then run the shipped Python adapter using
the existing issue #97 branch, without changing production `main`.
No secret is requested in chat.  Protected sandbox reservation tags
require a verified immutable-ref policy before acceptance is claimed.

The current project tools cannot provision/test the protected runner,
environment secrets and independently issued #80 grants.  They also
cannot prove that provider protection policies are installed.  Until
those are verified, four ordinary live mutation operations remain
NOT CERTIFIED; remote merge/check publishing stay explicitly DENIED
under their separate downstream gates.

## Verification state

| Criterion | State | Evidence / limitation |
| --- | --- | --- |
| Strict request/response grammar | Tested | issue-97-host-adapter |
| Authorization rejection and identity | Mock-tested | issue-97-auth-boundary |
| GitHub read normalization | Mock-tested | issue-97-github-provider-read |
| Four ordinary mutation paths | Mock-tested | issue-97-provider-mutations |
| Request reservation and retry | Mock-tested | issue-97-provider-transport |
| Concurrent same-ID comment | Mock-tested | Single side effect |
| Changed request with same ID | Mock-tested | Conflict in remote ledger |
| CLI stdin/stdout/stderr | Tested | issue-97-host-adapter |
| Real authenticated mutations | NOT VERIFIED | Provider sandbox needed |
| Persistent restart/reconcile on GitHub | NOT VERIFIED | Real tag/issue/PR |
| Scope policy issuer/revocation | NOT VERIFIED | Trusted verifier service |
| Real provider permissions/denials | NOT VERIFIED | Scoped credentials |
| Cross-platform acceptance | PASSED | Run 38081833496, 3 OS |
| Atomic protected-main merge | Denied | #542/#85 own enforcement |
| Authenticated check publisher | Denied | Trusted evidence not active |

The GitHub Actions Self CI workflow has read-only `contents` permission,
and the default issue-tier job does not provision mutation credentials or a
trusted authorization verifier.  Do not grant write access to an unreviewed
pull-request workflow just to manufacture positive evidence.  A real-provider
test must run in an independently approved sandbox or trusted CI context.

## Real provider smoke observations (not adapter certification)

- GitHub issue #624 was created as a disposable fixture.  Its title was
  updated, a comment was posted once (comment 6099874653), the records
  were fetched back, and the fixture issue was closed as completed.
- GitHub draft PR #616 was created and its metadata updated through the
  connected provider API without merging.
- These are **independent provider API probes**.  They do NOT execute the
  Python repo-host adapter or establish its authenticated idempotency and
  authorization semantics.  The live adapter acceptance gate stays open.

## Provider facts and limitations

The GitHub REST pull merge API accepts expected PR *head* `sha`, not the
separate destination-tip compare-and-swap demanded by #81.  A local GET
followed by an unprotected merge is not sufficient.  See
https://docs.github.com/en/rest/pulls/pulls

GitHub Git references can be created with a fully qualified ref and
Contents-write permission.  Request reservations must be protected from
later mutation/deletion by authorized deployment policy.  The adapter
never silently replays non-idempotent comments or PR creation after an
unknown outcome.  See https://docs.github.com/en/rest/git/refs

## Trusted live acceptance invocation

Provision a protected standalone verifier implementing the #80 decision
envelope.  Set `RWF_REPO_HOST_AUTH_COMMAND` to a JSON argv array with its
absolute executable path, not a local workspace file or caller role claim.
The verifier must authenticate the actor, issuer, delegation, standing
non-consuming policy, issue/candidate/integration scope, expiry/revocation,
and requested operation.  Its `scope_digest` is SHA-256 over the canonical
sorted-key compact UTF-8 JSON request sent by the adapter.

Use a disposable sandbox issue and two distinct sandbox branch refs.
Invoke `python scripts/probe-repo-host-github.py --help` for exact arguments;
provide repository, sandbox issue, source ref, target ref and unique run ID.
GitHub credentials need issue/PR mutation permissions and Contents-write
access for immutable request-reservation refs.  Keep the sandbox separate
from production protected-main integration.  Preserve the probe's JSON
evidence and record the provider and tested SHA.  Do not treat a mock verifier
as live authorization evidence.

## Completion gate

#97 must independently test ordinary mutations against real GitHub using
trusted verifier output, exact candidate and provider credentials, and a
durable sandbox ledger.  Exercise no/one/many requests, retries after process
restart, same-ID races, stale source/head, expired/revoked/missing grants,
permission denials, provider errors and malformed responses.

The final remote-protection acceptance of #85 and destination freshness of
#542 are downstream, NOT #97 prerequisites.  Do not add reverse edges.
Keep #97 OPEN and PR #616 DRAFT until its own real provider tests are GREEN.
No merge, required-check publication or production cutover is authorized.
