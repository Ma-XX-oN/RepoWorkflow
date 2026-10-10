# Portable Repository-Host Mutation Contract

Status: authoritative v1 contract for #81.  This is distinct from read-only
`REPO_INFO_CONTRACT.md` and the native dependency adapter.

## 1. Boundary

Core RepoWorkflow sends semantic requests to a configured repository-host
adapter.  The adapter alone owns provider API routes, permissions, pagination,
rate limits, and provider-specific identifiers.  The core may not inspect raw
provider responses to complete a mutation.

The adapter must support a read-only capability inquiry before a caller
attempts any mutation.  A false or missing capability blocks the dependent
mutation.  The caller must still handle a capability disappearing after inquiry.
No capability response grants authorization for an individual mutation.

## 2. Invocation and result envelope

The invocation is an executable command with one JSON request on stdin and
one JSON result on stdout.  The executable path comes from validated
configuration, not from issue data or a branch name.

Every request contains `schema_version: 1`, `operation`, `repository`,
`request_id`, and a typed `parameters` object.

- `repository`: the same stable owner/name identity as `repo-info`.
- `request_id`: stable non-empty caller-generated idempotency identity.
- Successful invocation exits zero and returns one JSON object.
- Failure exits nonzero, emits no successful JSON, and writes exactly one
  structured error JSON object to stderr (defined in section 6).
  Core treats an unknown outcome as unknown, never as success.
- No secrets, authorization tokens, or raw provider payloads appear in logs.

Response fields are `schema_version: 1`, `operation`, `repository`,
`request_id`, `status`, and `result`.  All identity fields must match
the request.  `status` on success is `applied` or `unchanged`.
No unexpected fields are accepted at this boundary.  `result` must be an
object conforming to the operation-specific shape below.  `unchanged` means
the desired state is already proven, never that the operation was skipped.

## 3. Supported semantic operations

`capabilities`: read-only; `parameters` is `{}` and `result` contains one
`operations` map with the six mutation operation names below as keys and
boolean values.  Unknown capability keys are rejected.  The successful status
is always `unchanged`; a missing or false entry blocks dependent mutations.
This is not an authorization check and does not consume a mutation request ID.

`issue.update`: takes positive issue number, optional title, and optional
open/closed state.  At least one field must change or the provider confirms
`unchanged`.  Returns exactly `{number, title, state}` with positive
integer number, non-empty title and `open|closed` state.  It may
never create a missing issue implicitly.  Reopening/closing is a
transition, not evidence of authorization.

`issue.comment`: takes positive issue number and non-empty comment body.
Returns exactly `{number, comment_id}`; number matches the requested issue,
and `comment_id` is a non-empty opaque string.  Replaying one request ID must
not create a second comment.

`pull_request.create`: takes exact source ref, target ref, expected source
head SHA, title, body, and draft boolean.  Returns a positive PR number,
exact source/target refs, and the provider-observed head SHA.  Result fields
are exactly `{number, source_ref, target_ref, head_sha, draft}`.
It never merges.
The request ID is bound to the exact source/target and initial head identity;
changed head on replay is a conflict, not implicit PR retargeting.
The adapter must check the exact expected source head at creation time.

`pull_request.update`: takes positive PR number, explicitly supplied
fields to change and an expected current head SHA.  Returns the PR number,
current head/target and draft/state.  Result fields are exactly
`{number, head_sha, target_ref, draft, state}`.  A moved head is a conflict.
An update may not implicitly merge or close a pull request.

`pull_request.merge`: takes PR number, exact tested head SHA, expected
destination SHA, verified candidate-eligibility reference, and explicit
merge authorization.  The adapter must refuse unless the provider can
enforce destination freshness and required server policies at acceptance.
A local GET followed by an unprotected merge is not an atomic operation.
Success returns exactly `{number, merged_head_sha, destination_sha}`.  Both
SHAs are provider-observed, and the destination SHA must represent the actual
post-merge target.  A provider without atomic acceptance must report
`unsupported` and perform no merge; it must never simulate safety.

`check.publish`: takes an exact candidate SHA, a unique check context,
one authenticated verification identity, and a terminal success/failure
conclusion.  A success may be published only after independent authenticated
candidate and evidence verification.  Caller-asserted `passed=true` is not
adequate authority.  Success returns exactly
`{candidate_sha, context, check_id, conclusion}` where `check_id` is an
opaque non-empty identifier and conclusion is `success|failure`.

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

## 6. Errors and authorization

Failures write one JSON object on stderr with exactly `schema_version`,
`operation`, `repository`, `request_id`, `error`, and `message`.  `error` is one
of `invalid_request`, `unsupported`, `unauthenticated`, `unauthorized`,
`not_found`, `conflict`, `rate_limited`, `transport_failure`,
`provider_failure`, `invalid_response`, or `unknown_outcome`.  `message` is
non-empty human-readable text without credentials or raw provider payload.
The other fields must match the request, even on failures.  An invalid input
that cannot be parsed into a request uses null for unparseable identity fields;
this exception cannot create a success result.  Failure stdout is empty.

Caller authorization is explicit evidence of actor, scope, operation and
expiry, verified at the actual mutation boundary against independent trusted
authority.  Local metadata and caller-declared role strings are never proof.
The adapter fails closed for missing, expired, revoked or insufficient rights.
Mutation authorization is independent of capability support, candidate
eligibility and test completion.  `pull_request.merge` additionally requires
remote-finalizer authority and a provider-enforced current-target gate.
The #80 authorization schema owns the authoritative evidence format; this
contract does not invent a competing token or role representation.

## 7. Parameter and identity grammar

Each operation's `parameters` is a JSON object with only the fields named
for that operation.  `capabilities` has an empty object.  `issue.update` has
`number` and one or more of `title`/`state`; `issue.comment` has `number` and
`body`; `pull_request.create` has `source_ref`, `target_ref`,
`expected_source_sha`, `title`, `body`, and `draft`;
`pull_request.update` has `number`, `expected_head_sha`, and one or more of
`title`, `body`, `draft`, `state`, `target_ref`;
`pull_request.merge` has `number`, `tested_head_sha`,
`expected_destination_sha`, `eligibility_ref`, `authorization_ref`;
`check.publish` has `candidate_sha`, `context`, `verification_ref`, and
`conclusion`.  Both references are non-empty opaque strings resolved and
verified by the adapter, not self-authorizing claims.

`request_id` is 1–128 ASCII characters from letters, digits, dot,
underscore, colon and hyphen.  It is scoped by repository and operation.
A retry of the same identity with different semantic parameters is a
conflict, never an alternative use of the identity.

An issue or PR number is a positive integer, not a boolean or numeric
string.  A Git commit identity is exactly 40 lowercase hexadecimal
characters.  `title` and `body` are UTF-8 strings; required titles,
comment bodies, refs and contexts are non-empty.  `draft` is a JSON
boolean.  `state` is `open|closed`; `conclusion` is `success|failure`.
`repository` is a non-empty
canonical `owner/name` from `repo-info`.  Source and target refs must be
explicit and unambiguous; a raw branch display name alone conveys no trust.
For update operations the caller must distinguish an omitted field (leave
unchanged) from an explicitly supplied empty body (clear it).

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
