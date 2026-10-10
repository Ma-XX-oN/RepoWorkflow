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
| Cross-platform acceptance | NOT VERIFIED | Hosted platform matrix |
| Atomic protected-main merge | Denied | #542/#85 own enforcement |
| Authenticated check publisher | Denied | Trusted evidence not active |

The GitHub Actions Self CI workflow has read-only `contents` permission,
and the default issue-tier job does not provision mutation credentials or a
trusted authorization verifier.  Do not grant write access to an unreviewed
pull-request workflow just to manufacture positive evidence.  A real-provider
test must run in an independently approved sandbox or trusted CI context.

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
