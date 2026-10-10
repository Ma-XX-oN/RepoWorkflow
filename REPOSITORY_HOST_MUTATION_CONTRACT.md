# Portable Repository-Host Mutation Contract

Status: draft for #81.  This is distinct from read-only
`REPO_INFO_CONTRACT.md` and the native dependency adapter.

## 1. Boundary

Core RepoWorkflow sends semantic requests to a configured repository-host
adapter.  The adapter alone owns provider API routes, permissions, pagination,
rate limits, and provider-specific identifiers.  The core may not inspect raw
provider responses to complete a mutation.

The adapter must support a capability inquiry before its first mutation.
An unavailable capability is an explicit failure, not a successful no-op.

## 2. Invocation and result envelope

The invocation is an executable command with one JSON request on stdin and
one JSON result on stdout.  The executable path comes from validated
configuration, not from issue data or a branch name.

Every request contains `schema_version: 1`, `operation`, `repository`,
`request_id`, and a typed `parameters` object.

- `repository`: the same stable owner/name identity as `repo-info`.
- `request_id`: stable non-empty caller-generated idempotency identity.
- Successful invocation exits zero and returns one JSON object.
- Failure exits nonzero, emits no successful JSON, and reports a reason on
  stderr.  Core treats an unknown outcome as unknown, never as success.
- No secrets, authorization tokens, or raw provider payloads appear in logs.

Response fields are `schema_version: 1`, `operation`, `repository`,
`request_id`, `status`, and `result`.  All identity fields must match
the request.  `status` on success is `applied` or `unchanged`.
No unexpected fields are accepted at this boundary.

## 3. Supported semantic operations

`capabilities`: read-only, returns a map of supported operation names to
booleans; a missing or false entry blocks dependent mutations.

`issue.update`: takes positive issue number, optional title, and optional
open/closed state.  At least one field must change or the provider confirms
`unchanged`.  Returns issue number, current title and state.  It may never
create a missing issue implicitly.

`issue.comment`: takes positive issue number and non-empty comment body.
Returns an opaque stable comment identity.  Replaying one request ID must
not create a second comment.

`pull_request.create`: takes exact source ref, target ref, title, body, and
draft boolean.  Returns a positive PR number, exact source/target refs, and
the provider-observed head SHA.  It never merges.

`pull_request.update`: takes positive PR number, explicitly supplied
fields to change and an expected current head SHA.  Returns the PR number,
current head/target and draft/state.  A moved head is a conflict.

`pull_request.merge`: takes PR number, exact tested head SHA, expected
destination SHA, verified candidate-eligibility reference, and explicit
merge authorization.  The adapter must refuse unless the provider can
enforce destination freshness and required server policies at acceptance.
A local GET followed by an unprotected merge is not an atomic operation.

`check.publish`: takes an exact candidate SHA, a unique check context,
one authenticated verification identity, and a terminal success/failure
conclusion.  A success may be published only after independent authenticated
candidate and evidence verification.  Caller-asserted `passed=true` is not
adequate authority.

## 4. Idempotency and concurrency

An adapter must persist or resolve operation identity sufficiently to avoid
duplicate side effects on retry.  If the provider cannot establish whether
a prior mutation occurred, the adapter returns an unknown-outcome error and
requires reconciliation; it must not blindly replay a non-idempotent request.

Expected SHAs are mandatory for operations that touch a PR head, destination
ref, or required check.  A stale expected SHA fails with `conflict` and no
intentional mutation.  Only a provider-enforced atomic acceptance can close a
race between the final local read and a merge.

An unsupported operation, missing permission, rate limit, invalid response,
missing issue/PR, stale candidate, network failure, and unknown outcome are
distinct failure classes; none may be normalized to `unchanged`.

## 5. Core invariants

- Mutation never follows from `repo-info` discovery alone.
- Branch names do not establish candidate eligibility, ownership, or rights.
- GitHub-specific check names, payload shapes, URLs and token scopes belong
  to adapter configuration and provider implementation.
- Core does not infer authorization from a GREEN local test or PRELIM tag.
- A provider result must not be accepted if the request and response
  identities differ.
- Adapter calls must not silently modify local Git HEAD, index or worktree.

## 7. Parameter and identity grammar

`request_id` is 1–128 ASCII characters from letters, digits, dot,
underscore, colon and hyphen.  It is scoped by repository and operation.
A retry of the same identity with different semantic parameters is a
conflict, never an alternative use of the identity.

An issue or PR number is a positive integer, not a boolean or numeric
string.  A Git commit identity is exactly 40 lowercase hexadecimal
characters.  `title` and `body` are UTF-8 strings; required text is
non-empty.  For update operations the caller must distinguish an omitted
field (leave unchanged) from an explicitly supplied empty body (clear it).

`check.publish` may name a stable required context only when provider
configuration authorizes that context.  Its proof is a reference to
authenticated evidence, not a caller-supplied success boolean or an
unverified test log.

The adapter must reject unexpected operation parameter keys instead of
silently dropping them.  An adapter must also reject a response that omits
or contradicts the requested repository, operation, request ID, or expected
head/destination facts.

## 8. Acceptance matrix

Contract tests must cover zero/one/many requests and idempotent repeats,
changed inputs and changed expected SHAs, invalid schema and identifiers,
malformed/extra fields, unsupported capabilities, permission denial,
provider timeout after possible mutation, and restart/reconciliation.

Provider tests must demonstrate a real issue update, one comment per request
ID, PR creation without merge, stale PR head refusal, and fail-closed
merge/check publishing when protection or authenticated evidence is absent.

Actual GitHub protected-main enforcement remains owned by #85; #104 owns
the provider-neutral exact-candidate eligibility decision and #542 owns
destination-tip freshness.  Defining this contract does not configure
GitHub permissions, publish a trusted status check, or authorize a merge.
