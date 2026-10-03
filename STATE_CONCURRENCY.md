# Concurrent Durable State Mutation Contract

Status: authoritative concurrency and writer-identity contract for durable
`.repoworkflow/` mutations.

This document extends [STATE_LAYOUT.md](STATE_LAYOUT.md).  That document decides
where a fact is authoritative; this one defines how independent writers may
change durable repository facts without silently overwriting one another.

## 1. Scope

This contract applies to mutable durable/shared records under committed
`.repoworkflow/`.

Clone-common workspace claims already use a local CAS namespace.  They are not
made globally authoritative by this contract, and worktree-local execution
context remains local.

## 2. Durable mutation identity

Every durable mutation is evaluated against an exact authoritative input
identity.

A mutation request contains:

- the durable record key/type being changed;
- the schema version understood by the writer;
- an exact expected record revision;
- a stable writer identity;
- a per-execution session identity;
- the semantic replacement value or transition.

The writer identity identifies the agent/process identity responsible for the
mutation across retries.  The session identity distinguishes separate
executions by that writer.

Neither identity establishes workflow authority by itself.  Authorization and
workflow legality are separate semantic gates.

Writer/session identity must not be inferred from branch name, worktree path,
commit author, operating-system user, or process ID.

## 3. Record revisions

Every mutable durable record has a monotonically increasing integer revision.

Creation starts at revision `0`.  A successful mutation from revision `N`
produces revision `N + 1`.

The expected revision is mandatory for replacement of an existing record.

A writer that read revision `N` cannot silently replace revision `N + 1`,
even if the later value was written by the same writer or session.

Revision comparison is record-scoped.  Unrelated records do not share one
global revision counter.

## 4. Compare-and-swap rule

Durable mutation is compare-and-swap (CAS):

1. read and validate the current record;
2. construct a semantic mutation against its exact revision;
3. immediately before publishing, verify the authoritative input still has the
   expected identity/revision;
4. publish the new value atomically;
5. verify the published value is the intended next revision/value.

A mismatched revision or authoritative input is a conflict, not permission to
retry the write against the newer state.

The caller may reread, recompute the semantic transition, and submit a new
mutation only after proving that transition remains legal.

## 5. Independent writers

Two agents may mutate different durable record keys concurrently.

Their writes are non-conflicting when neither mutation changes or invalidates
an authoritative input consumed by the other.

For the same record/revision, at most one competing mutation may succeed.

If two semantic operations touch several records that together form one
invariant, they are one transaction for conflict purposes.  Implementations
must not split such an invariant and call the partial writes independent.

## 6. Conflict handling

A detected conflict fails closed and reports enough information to reread the
authoritative state.

Conflict resolution is deterministic:

- never choose a winner by wall-clock timestamp;
- never choose a winner by last-writer-wins;
- never merge safety-critical values field-by-field unless that merge is
  explicitly defined by the record's semantic contract;
- never overwrite merely because writer identity matches;
- never downgrade a conflict to success because the desired value happens to
  resemble the current value.

A semantic layer may define an idempotent already-applied result.  It must
prove equivalence explicitly rather than relying on storage-layer guessing.

## 7. Atomic publication

A durable record replacement must be atomic at the storage boundary: readers
observe either the complete prior value or the complete successor value.

Temporary/staging files are not authoritative state and must not be interpreted
as records after interruption.

A failed publication leaves the prior authoritative value intact.

For repository history, a successful local file replacement is not by itself a
cross-clone global lock.  Integration against the shared repository must still
use exact candidate/base identity and server-side integration controls.

## 8. Multi-record transitions

A transition that must change multiple durable records atomically must declare
its complete read set and write set before publication.

The implementation must verify every authoritative input in the read set is
still current before exposing any successor as a completed transition.

If the storage mechanism cannot atomically publish the whole write set, it must
use a recoverable transaction protocol whose durable state distinguishes:

- prepared but not committed;
- committed;
- aborted/recoverable.

Partial publication must never be reported as successful workflow state.

The recovery rules for interrupted transactions are defined by #100.

## 9. Writer identity and auditability

Successful durable mutations retain enough provenance to answer:

- which stable writer proposed the mutation;
- which execution/session performed it;
- which prior revision it consumed;
- which successor revision it produced.

Provenance is audit evidence, not ownership of the durable fact.  A later
authorized writer may legally advance the same record using CAS.

Secrets, access tokens, host credentials, and transient process identifiers
must not be persisted as writer identity.

## 10. Local versus durable state

Local state may reference a durable record/revision but cannot advance it.

In particular:

- a clone-common workspace claim cannot reserve a durable mutation globally;
- a worktree-local current issue cannot become a shared active-issue slot;
- deleting local state cannot delete durable history;
- merging a branch cannot reinterpret clone-local files as authoritative facts.

There is no shared mutable global `active_issue` record.

## 11. Cross-clone behaviour

Independent clones cannot coordinate through clone-common locks.

When two clones start from the same durable revision, both may prepare work,
but shared integration must detect that the authoritative base/candidate has
changed before the second conflicting mutation becomes canonical.

RWF must describe this as optimistic concurrency, not global locking.

## 12. Required failures

Fail closed on at least:

- unsupported record schema;
- missing/invalid expected revision for an existing record;
- stale expected revision;
- malformed or absent writer identity;
- changed authoritative input/read-set member;
- illegal semantic transition;
- incomplete/ambiguous multi-record transaction state.

A conflict must not mutate the prior authoritative record.

## 13. Required implementation coverage

The generic state store in #101 must prove at least:

1. revision-zero creation and monotonic successor revisions;
2. stale CAS rejection without mutation;
3. two writers racing one revision yield exactly one successor;
4. independent record keys can advance without a global active-record lock;
5. malformed writer/session identity fails closed;
6. atomic replacement never exposes a partial JSON record;
7. failed replacement preserves the prior authoritative value;
8. clone-local state cannot satisfy or bypass a durable CAS;
9. provenance records expected and resulting revisions;
10. multi-record transitions either commit completely or remain explicitly
    recoverable.

#100 defines reconstruction/recovery after stale or interrupted state.  #101
implements the provider-neutral storage primitives that enforce this contract.
