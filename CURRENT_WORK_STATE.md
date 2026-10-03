# Worktree-Local Current Work and Re-entry Schema

Status: authoritative schema/invariant contract for local RWF current-work
context.

This document defines local execution/navigation state only.  Durable issue
lifecycle and relationship authority remain in `ISSUE_LIFECYCLE_STATE.md` and
`RELATIONSHIP_GRAPH.md`.

## 1. Placement and authority

Current-work state belongs to one worktree and lives under:

```text
<git-dir>/repoworkflow/current-work/
```

It is not clone-common claim state and is never committed.

A linked worktree has its own current-work namespace.  Two worktrees in the same
clone therefore cannot overwrite one another's current issue/navigation state.

Local current-work state may reference durable facts.  It cannot create,
advance, complete, abort, or otherwise replace durable workflow history.

## 2. Schema version

The initial schema version is `1`.

The semantic value has this shape:

```json
{
  "schema_version": 1,
  "current": {
    "issue": "64",
    "lifecycle_revision": 3,
    "relationship_revision": 7
  },
  "resume": null,
  "selected_issue": "64",
  "cache_sources": {
    "lifecycle_revision": 3,
    "relationship_revision": 7
  }
}
```

All issue identifiers are canonical positive decimal strings without leading
zeroes.

## 3. Current execution context

`current` is either `null` or contains exactly:

- `issue`;
- `lifecycle_revision`;
- `relationship_revision`.

Both revisions are non-negative integers naming the exact durable inputs that
established the local context.

A current context is valid only while those durable references remain the
expected authoritative inputs for the owning workflow operation.

A stale current context never advances or overwrites newer durable state.

## 4. Re-entry pointer

`resume` is either `null` or has the same three fields as `current`.

It records the durable issue/revisions from which local work may be considered
for re-entry after the owning transition clears `current`.

A resume pointer is navigation/execution convenience, not permission or
ownership.

In particular, it does not:

- recreate a worker/session claim;
- make an aborted issue active;
- prove that re-entry is currently legal;
- satisfy a dependency;
- fabricate missing durable history.

The re-entry operation must reread current durable lifecycle and relationship
authority before acting.

## 5. Navigation

`selected_issue` is a canonical issue identifier or `null`.

Selection is a local navigation hint.  It may identify an issue other than
`current.issue` and never changes workflow state.

Commands that require an active current issue must use `current`, not
`selected_issue`.

## 6. Derived cache identity

`cache_sources` is either `null` or contains exactly:

- `lifecycle_revision`;
- `relationship_revision`.

It identifies the durable inputs consumed by a reconstructable local
projection/cache.

Cached derived payload is not part of schema version 1.  A consumer may use the
source identity to decide whether separately defined reconstructable cache data
is stale.

A cache whose source revisions no longer match authority may be discarded and
rebuilt.  Cache loss never changes durable state.

## 7. Start projection

After a successful durable issue-start/re-entry transition, local current-work
may project that result as:

- `current.issue` = the started issue;
- `current.lifecycle_revision` = exact resulting durable lifecycle revision;
- `current.relationship_revision` = exact relationship revision consumed by
  the start;
- `selected_issue` = the issue;
- `resume` = `null`.

The durable transition is authoritative.  A local write failure must not make a
failed durable transition appear successful; the owning multi-record workflow
defines rollback/recovery.

## 8. Abort projection

After a successful durable abort transition:

- `current` becomes `null`;
- `resume` may reference the aborted issue and exact resulting durable
  lifecycle/relationship revisions;
- `selected_issue` may remain on the aborted issue for navigation.

Clearing local current state before durable abort succeeds must not be reported
as a successful abort.

## 9. Missing and stale local state

Missing current-work state does not erase durable history.

When the file is absent, the local projection is:

```text
current = null
resume = null
selected_issue = null
cache_sources = null
```

This does not imply that no durable issue is active elsewhere.

A stale pure cache may be rebuilt.  A stale current/resume pointer that cannot
be uniquely reconstructed is preserved for diagnosis and action stops rather
than guessing a replacement.

## 10. Reconstruction

Reconstruction follows `STATE_RECOVERY.md`.

Durable facts may support rebuilding a navigation/cache projection only when
one result is uniquely determined.  They must not reconstruct:

- worker ownership;
- session identity;
- a lost claim;
- ambiguous current issue;
- authorization;
- a transition lacking durable evidence.

Repeated reconstruction against unchanged authority is idempotent and does not
advance durable revisions.

## 11. Record concurrency

The #172 semantic store uses #101 atomic record/CAS primitives in the
worktree-local namespace.

A local replacement requires its expected local record revision.  Stale local
writers fail explicitly.

Local CAS coordinates mutations of this worktree's current-work record only.
It is not a cross-worktree or cross-clone workflow lock.

## 12. Failure semantics

Reject at least:

- unsupported schema versions;
- missing/unknown fields;
- invalid issue identifiers;
- invalid durable revisions;
- current/resume objects with incomplete source identity;
- stale durable references when an operation requires freshness;
- attempts to use navigation/cache state as durable authority.

Malformed local state is not silently interpreted as an empty current context
unless it is a separately defined fully reconstructable cache.

## 13. Required implementation coverage

#172 must prove at least:

1. two linked worktrees have distinct current-work records;
2. current/resume durable references round-trip exactly;
3. stale lifecycle or relationship references are detected;
4. missing local state does not erase or alter durable history;
5. abort projection clears current while preserving a valid resume pointer;
6. re-entry rereads durable authority rather than trusting resume;
7. selected issue does not become current issue implicitly;
8. reconstructable cache loss is safe and deterministic;
9. ambiguous current context remains unset;
10. stale local CAS cannot overwrite a newer local record;
11. local writes cannot advance durable lifecycle/relationship records.

Known consumers are #64, #98, #72, and #87.
