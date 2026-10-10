# Authorization Evidence Contract

Status: authoritative v1 semantic contract for issue #80.
Scope: repository workflow authority, independent of Git author, writer
provenance, test evidence, provider transport and local workspace claims.

## 1. Authority model

Only independently verified actor identity and a trusted authorization issuer
can grant capabilities.  Neither `RWF_WRITER_ID`, `RWF_SESSION_ID`, a
repository commit author, CI job identity, branch name, local configuration,
or a user-supplied role string grants permission.  Writer/session values from
`STATE_CONCURRENCY.md` remain mutation provenance, not actor authentication.

The fixed role vocabulary is:
- `developer`: ordinary source and issue work within assigned scope;
- `trusted_local_tester`: local verification within assigned scope;
- `ci_test_runner`: authenticated hosted execution within assigned scope;
- `security_administrator`: policy and grant administration;
- `remote_finalizer`: explicitly delegated remote integration actions.

Roles form a set of capabilities, not a hierarchy.  A security administrator
is not automatically a remote finalizer; a CI runner cannot acquire finalizer
power from successful tests.  Multiple roles require separate explicit grants.
A remote finalizer's privileged authenticated provider identity is verified
at the remote mutation boundary, independently of Git author and local state.

## 2. Canonical evidence records

A durable authorization fact is a UTF-8 JSON object with only the following
top-level fields.  All named fields are required unless stated otherwise.

```text
schema_version: 1
grant_id: non-empty immutable opaque identifier
revision: non-negative integer
issuer: {authority_id, subject_id, authentication_ref}
subject: {actor_id, authentication_ref}
role: one of the five role strings in section 1
capabilities: non-empty sorted unique array of capability identifiers
scope: {repository, issue_numbers, candidate_sha, integration_id,
        destination_ref, expected_destination_sha, release_class}
issued_at: canonical UTC instant
not_before: canonical UTC instant
expires_at: canonical UTC instant
status: active | revoked
revoked_at: null or canonical UTC instant
revocation_ref: null or non-empty independent trusted evidence reference
max_uses: positive integer or null for non-consuming policy
uses: non-negative integer
binding: {issuer_signature_ref, policy_revision, source_record_sha}
provenance: {writer_id, session_id, expected_revision}
```

All fields are semantically validated; unknown fields and unsupported schema
versions fail closed.  Identifiers, references and signatures are not trusted
merely because they appear in the JSON.  An authenticated verifier must
resolve references to a trusted issuer, identity provider and immutable facts.
The authorization record does not embed credentials, bearer tokens or secrets.

`repository` is canonical owner/name.  `issue_numbers` is a sorted unique
array of positive integers.  `candidate_sha` and
`expected_destination_sha` are either null or exact 40-character lowercase
Git commit hashes.  `integration_id` and `destination_ref` are either null
or non-empty exact identities.  `release_class` is exactly `patch`,
`minor`, `major`, or null.  Null means that dimension is not constrained
only when the issuing policy explicitly authorizes such breadth.  Absence or
null must never be interpreted by a consumer as wildcard authority without
that independently verifiable policy.  An empty issue list does not mean
all issues unless an explicit verified policy says so.

A grant for `major` release authorization is distinct from patch or minor
authorization.  A consumer cannot infer major authorization from ordinary
release permission or from a more permissive role name.

## 3. Capability and scope

Capability identifiers refer to canonical semantic actions, not provider API
route names.  The baseline set is `issue.update`, `issue.comment`,
`pull_request.create`, `pull_request.update`, `pull_request.merge`,
`check.publish`, `policy.grant`, and `policy.revoke`.
Unknown capabilities fail closed.  Capabilities never imply each other.

Evaluation requires exact repository, actor, role and requested capability.
Every constrained scope dimension must match the requested issue, candidate,
integration, destination and release class.  A new candidate commit, changed
destination tip, different issue or integration is a new authorization query;
a previously issued candidate-bound grant does not silently transfer.

Requested release class `major` requires explicit major-class authority.
A broad policy and a specific one-time grant remain distinct evidence kinds
in the evaluation record; a one-time operator consent is not promoted into
repository-wide standing policy.

## 4. Trusted origin and delegation

An issuer is trusted only through independently validated repository policy
and authenticated issuer delegation, including the right to grant the exact
role, capability, scope and lifetime.  A self-signed local record or caller
assertion is insufficient.  Delegation cannot increase issuer privileges.
An administrator may grant only what its independently verified delegation
permits; administrator role alone grants no bypass.

Actor authentication has an evidence reference resolving to subject identity,
authenticator, audience, expiry and revocation status.  The authorization
verifier evaluates it at the moment of the protected operation.  Provider
token possession does not establish workflow scope.  The remote finalizer
must additionally prove the provider-authenticated principal and its
privileged remote permissions.

## 5. Lifetime, consumption and invalidation

Validity requires a trusted issuer, verified binding, matching subject and
scope, `not_before <= evaluation_time < expires_at`, active status and
unconsumed quota.  Time comes from a trusted evaluator clock, not from a
caller-controlled timestamp.  Expiry and revocation are never repaired by
replaying an older copy.  A policy revision, source identity or provider
permission change triggers re-evaluation against the current authority.

A one-use grant has `max_uses: 1` and `uses: 0` initially.  Its successful
protected operation consumes the grant atomically with the operation's
authoritative decision or through a recoverable transaction explicitly
linking both results.  An unsuccessful operation does not become authorized
by consuming evidence.  A partially applied or unknown-outcome operation
requires reconciliation before any retry; it cannot consume twice or repeat
a non-idempotent mutation.  The consumption record binds request ID, grant
revision, exact operation, candidate and final provider-observed result.

A repeated identical request ID may return the proven previous decision and
result without consuming again.  A changed request body or scope using the
same ID fails `conflict`.  A fresh request cannot reuse an already exhausted
one-time grant.  Standing repository policy may be non-consuming
(`max_uses: null`) only when that policy was independently verified.

Revocation produces a new authoritative record revision with `status:
revoked`, `revoked_at`, and `revocation_ref`.  No consumer may continue to
use a cached pre-revocation authorization.  A revocation does not undo a
completed authorized action; it prevents later authorization decisions.

## 6. Concurrency and persistence

Durable grant records belong to the repository-controlled
`.repoworkflow/` authority under `STATE_LAYOUT.md`.  Their revision,
writer/session provenance and CAS publication follow
`STATE_CONCURRENCY.md`.  The authoritative record key is grant ID.
Creation starts at revision zero; replacement requires the exact expected
revision.  Concurrent updates to a grant have one winner or a recoverable
transaction; last-writer-wins is forbidden.  Identity matching does not
bypass CAS.

A revocation and consumption affecting the same grant must serialize against
the same authoritative revision.  One cannot succeed using stale authority
while the other becomes canonical.  Across clones, a local CAS does not
replace server-side authority and destination freshness controls.

When several records jointly determine one authorization decision, the
complete read set (grant, actor proof, issuer delegation, policy, revocation,
scope and candidate identity) must be revalidated at the publication gate.
A multi-record write uses atomic commit or the prepared/committed/aborted
transaction rules in `STATE_RECOVERY.md`.  Prepared is never authorized.
Ambiguous partial state fails closed.

## 7. Decision envelope and failure semantics

The evaluator returns an explicit decision record with:
`schema_version`, `request_id`, `grant_id`, `grant_revision`,
`actor_id`, `capability`, `scope_digest`, `policy_revision`,
`evaluated_at`, `decision`, and `reason`.
`decision` is `allow` or `deny`; a denied or unverifiable request never
produces an authorization usable by a provider adapter.  An allow decision
is bound to a single operation request and exact current authoritative input
identities.  Evaluation alone does not perform the protected mutation.

Failure reasons distinguish invalid schema, missing authentication, unknown
issuer, insufficient delegation, denied capability, scope mismatch, not yet
valid, expired, revoked, exhausted, stale revision/candidate, changed policy,
conflict, unavailable authority and unknown outcome.  Invalid/unavailable
proof never degrades to allow, nor to a supposedly authorized unchanged
result.  Logs show non-secret reason and immutable references only.

`repo-host` mutations defined by #81 must verify this grant independently
at the mutation boundary.  The exact-candidate eligibility, validation,
provider required-check and atomic remote acceptance gates remain separate.
An authorization allow never overrides their denial.

## 8. Reconstruction and compatibility

After clone loss, reconstruct only from verified durable authorization
history and its referenced authoritative issuers, delegations, revocations,
consumption facts and candidate identities.  Local claims, session values,
uncommitted files, Git ancestry, green tests or cached decisions cannot
recreate a grant.  Missing, contradictory, unsupported or inaccessible
authority yields deny with an actionable diagnostic.

For a historical decision, preserve the exact validated grant revision and
policy version used at that instant, without treating historical validity as
current permission.  Recovery is idempotent, never increments uses merely
because reconstruction ran, and never silently widens scope.

This contract defines semantics, not a new authentication-token format or
production enforcement activation.  #86 consumes authorization decisions;
#548 owns evidence provenance rather than the authorization schema.
Remote-finalizer privilege and hosted publisher enforcement remain explicit
consumer responsibilities.

## 9. Acceptance obligations

Independent tests must cover the acceptance matrix in
`AUTHORIZATION_EVIDENCE_TEST_MATRIX.md`.  Implementations must separately
prove:
- issuer/actor authenticity and non-hierarchical role separation;
- policy versus one-time grant and exact candidate/issue/integration scope;
- timed validity, revocation, consumption and unknown-outcome recovery;
- two writers racing consumption/revocation, stale CAS and clone restart;
- major-release distinction and denial without finalizer identity;
- fail-closed unavailable authority and provider-side revalidation.

A documentation-only CI success does not certify those runtime/provider
behaviours.  No GitHub permission, protected branch, hosted status, PR merge
or production cutover is performed by publishing this contract.
