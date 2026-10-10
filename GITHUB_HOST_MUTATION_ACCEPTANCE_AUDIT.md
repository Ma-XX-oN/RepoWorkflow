# Issue #97 — GitHub Mutation Adapter Acceptance Audit

Status: OPEN.  This document records tested implementation boundaries and
unmet provider/security gates.  It is not a DONE certificate.

## Contract and provenance

- #81: REPOSITORY_HOST_MUTATION_CONTRACT.md, v1, exact handoff
  1241bcec7802a753f6ab3db43c335bba9f802fbc (PR #605).
- #80: AUTHORIZATION_EVIDENCE_CONTRACT.md, v1, exact handoff
  fdc3ee15b03173d6d2fbbd2bd71abf7314e3ca2e (PR #614).
- This branch: issue-97-github-host-mutation-adapter.
- Current draft PR: #616, base issue-81-host-mutation-contract.

## Current implementation

- `adapters/repo-host-github.py` parses one strict JSON request from stdin.
- The seven operation names are recognized.  `capabilities` is the only
  successful operation and advertises all six mutations as unavailable.
- It rejects malformed envelopes, duplicate JSON keys, unsupported schema,
  invalid identity/ref/number/SHA types and unexpected parameters.
- Errors have one structured JSON object on stderr, no success stdout and
  a nonzero exit.  Success has one JSON object on stdout.
- `adapters/repo_host_github_reads.py` provides normalized read-only GitHub
  issue, PR and branch observations, with identity, type and error checking.
- The two test modules have issue-scoped test catalogue groups.
- No implemented operation currently creates, updates, merges or publishes
  anything at GitHub.  This is an intentional safety restriction.

## Acceptance coverage

| Contract behavior | Status | Evidence / remaining work |
| --- | --- | --- |
| JSON request/result/error envelopes | Partial | Unit + CLI tests |
| Capability inquiry | Partial | Explicit all-false map |
| Issue update | Missing | Trusted auth + mutation + live test |
| Issue comment | Missing | Trusted auth + durable dedup + live test |
| PR create | Missing | Exact head binding + dedup + live test |
| PR update | Missing | Expected-head enforcement + live test |
| PR merge | Missing | Atomic destination + protection + auth |
| Check publish | Missing | Authenticated proof + protected context |
| Provider identity observations | Partial | Mocked GET tests |
| Real provider negative/positive tests | Missing | Live sandbox |
| Cross-restart idempotency | Missing | Durable claim/reconciliation |
| Concurrent writer race coverage | Missing | Provider transaction tests |
| Windows/macOS/Linux acceptance | Missing | Hosted matrix |

## Provider boundaries verified against documentation

The GitHub REST PR merge endpoint documents an optional `sha` for the
expected PR *head*, but does not provide the contract's separately required
`expected_destination_sha` parameter.  A GET of the destination followed
by this merge endpoint is not an atomic destination compare-and-swap.
See: https://docs.github.com/en/rest/pulls/pulls

For issue comments, do not assume repeated POST requests with the same RWF
request ID are deduplicated.  The documented comments endpoint does not
specify an RWF idempotency key.  Implement durable reservation, proof of
prior effect, and unknown-outcome reconciliation before activating comments.
See: https://docs.github.com/en/rest/issues/comments

## Authorization and capability gate

#80 specifies canonical grants, trusted actor/issuer proofs, scope, expiry,
revocation and CAS consumption semantics.  It is a contract, not an
executable trusted issuer/verifier.  No Git author, session, token possession,
local claim or security-administrator role alone is a grant.

The adapter must independently verify that authority at mutation time.
A trusted verifier, durable reconciliation and protected provider acceptance
must be implemented and independently tested before any capability becomes
true.  #85 owns actual protected-main enforcement; #542 owns acceptance-time
destination freshness.  Neither the unmerged #80 contract nor a passing
local test is proof that those remote gates are active.

## Completion criteria

Do not post DONE or close #97 until all six required mutations have valid
provider normalization, rights checking, idempotency and failure behavior,
real-provider tests, exact-candidate CI evidence, and an auditable handoff.
Do not merge this draft PR or enable risky calls as a workaround.
