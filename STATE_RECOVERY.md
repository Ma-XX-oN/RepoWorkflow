# Durable and Local State Recovery Contract

Status: authoritative stale-state reconstruction and recovery contract for RWF
state.

This document extends [STATE_LAYOUT.md](STATE_LAYOUT.md) and
[STATE_CONCURRENCY.md](STATE_CONCURRENCY.md).  It defines what may be
reconstructed after local-state loss or interruption and how RWF responds to
stale or incomplete state.

## 1. Recovery principle

Recovery derives convenience/execution state from authoritative facts.  It does
not manufacture authoritative facts.

For the same validated durable inputs and repository identity, reconstruction
must produce the same semantic result.

When required authority is missing, contradictory, unsupported, or ambiguous,
recovery fails closed with the facts that prevent a unique result.

## 2. Authority order

Recovery evaluates state by its declared scope:

1. validated durable repository facts are authoritative for workflow history,
   relationships, validation, authorization, and integration facts;
2. clone-common state is authoritative only for coordination inside that clone;
3. worktree-local state is authoritative only for that worktree's execution
   context.

A lower scope cannot override a newer or contradictory higher-scope fact.

Git branch/worktree topology may corroborate operational context but cannot
create issue relationships or workflow history.

## 3. Reconstructable local state

Local state is reconstructable only when durable and observable repository
facts determine one valid local projection.

Examples that may be reconstructed when uniquely determined include:

- a local reference to a known durable issue/revision;
- a workspace's durable workflow summary;
- derived readiness/blocker projections;
- cache entries whose complete source facts are durable;
- navigation/resume hints that merely point at uniquely identified existing
  work.

Reconstruction must not recreate:

- an expired/lost worker claim as though it were still owned;
- a writer/session identity;
- an authorization that is not durable;
- a completed transition lacking durable commit evidence;
- a relationship inferred only from branch ancestry;
- a shared mutable active-issue selection.

If several valid local contexts are possible, RWF reports the ambiguity rather
than selecting one.

## 4. Stale-state detection

A local record that references durable state must retain enough source identity
to detect staleness.

Where applicable this includes:

- durable record key/type;
- schema version;
- durable revision or exact candidate identity;
- repository/worktree identity needed to establish scope.

Local state is stale when any authoritative input it consumed has changed,
disappeared, become unsupported, or no longer validates.

Staleness is semantic, not timestamp-based.  File modification time, wall-clock
age, and process lifetime do not prove freshness.

## 5. Stale local state

Stale local state is never silently promoted or written back into durable
state.

If it is a pure cache/projection, RWF may discard and deterministically rebuild
it from current authority.

If it contains non-authoritative user/agent execution context that cannot be
uniquely reconstructed, RWF preserves it for diagnosis and stops actionably.

A stale workspace claim remains governed by the clone-local claim contract; it
cannot be renewed merely because durable state still mentions the same issue.

## 6. Missing local state

Deleting clone-common or worktree-local state does not erase durable workflow
history.

After local-state loss:

- durable projections may be rebuilt;
- operational workspace mappings may be rediscovered only from explicit,
  unambiguous Git/local facts;
- worker ownership/claims are not recreated;
- session identity is not recreated;
- ambiguous current-work selection remains unset.

A fresh clone therefore starts without inheriting another clone's claims or
sessions.

## 7. Obsolete schema/state

Unsupported durable schema fails closed.  Recovery must not guess a migration.

Unsupported local schema may be discarded only when the record is proven to be
a fully reconstructable cache/projection.  Otherwise it is preserved and an
explicit migration/recovery action is required.

Migration changes are semantic mutations and must obey the concurrency contract
when they affect durable records.

## 8. Interrupted single-record writes

Atomic durable replacement means an interruption leaves either the prior
authoritative record or the complete successor.

Temporary/staging artifacts are never authoritative.

Recovery may remove an abandoned staging artifact after proving it is not a
committed record and cannot contain the only copy of non-reconstructable local
work.

A malformed authoritative record is not treated as an empty/missing record.

## 9. Interrupted multi-record transactions

A recoverable multi-record transaction has a durable transaction identity and
declared read/write set.

Its durable state distinguishes at least:

- `prepared`: intent/read-set/write-set recorded, not committed;
- `committed`: the transaction's complete successor is authoritative;
- `aborted`: the transaction will not become authoritative.

Recovery rules:

1. `committed` is replayed/finished idempotently until every materialized
   record reflects the committed successor;
2. `aborted` may clean up prepared/staging material without publishing it;
3. `prepared` is never assumed committed;
4. a `prepared` transaction may be committed only by the normal transaction
   protocol after revalidating every authoritative input;
5. changed/missing read-set inputs make the prepared transaction stale and it
   must abort or stop for explicit resolution;
6. contradictory transaction evidence is ambiguous/unrecoverable and fails
   closed.

No partially materialized write set is exposed as a successful workflow
transition.

## 10. Idempotent recovery

Recovery operations must be safe to repeat after another interruption.

Repeating recovery against unchanged authoritative inputs produces the same
semantic state and does not advance durable revisions merely because recovery
ran again.

If another writer advances authority during recovery, the recovery attempt
detects the changed identity/revision and restarts from a fresh read rather
than overwriting it.

## 11. Actionable failure

An unrecoverable/ambiguous result reports, where applicable:

- affected record/transaction;
- expected and observed schema/revision/candidate identity;
- which authoritative inputs are missing or contradictory;
- which local artifact was preserved;
- whether retry after reread is safe;
- what explicit human/semantic decision is required.

The diagnostic must not suggest destructive cleanup when doing so could erase
the only copy of local work.

## 12. Git and repository history

Git history can establish exact committed file/candidate identity and whether a
durable state version exists in a particular repository revision.

It cannot by itself infer:

- issue dependency;
- umbrella ownership;
- authorization;
- worker ownership;
- active issue;
- whether an uncommitted local transition semantically succeeded.

Recovery uses Git only for facts Git actually records.

## 13. Local-only mode

In `rwf init local-only`, the same authority ordering applies inside the local
footprint, but there is intentionally no shared durable repository authority.

Recovery must not describe locally materialized workflow facts as
cross-clone/shared truth.

Loss of the only local-only copy of a non-reconstructable fact is unrecoverable.

## 14. Required implementation coverage

The generic state store/recovery support in #101 and its consumers must prove:

1. stale local revision/candidate references are detected;
2. reconstructable cache loss produces the same projection from equivalent
   durable inputs;
3. missing claims/sessions are not recreated from durable state;
4. ambiguous current-work/workspace context remains unset and reports why;
5. malformed durable state fails closed rather than becoming empty state;
6. unsupported local cache schema is rebuilt only when fully reconstructable;
7. interrupted single-record publication preserves a complete authoritative
   record;
8. prepared transactions are never reported committed;
9. committed transaction replay is idempotent;
10. changed transaction read-set inputs prevent stale publication;
11. repeated recovery does not spuriously advance durable revisions;
12. recovery never derives semantic relationships from Git ancestry.

#101 implements the generic storage primitives against the #99 concurrency and
this recovery contract.
