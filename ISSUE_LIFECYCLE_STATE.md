# Durable Issue Lifecycle Record Schema

Status: authoritative schema/invariant contract for durable RWF issue lifecycle
state.

This document defines the semantic value persisted by the canonical lifecycle
store implemented by #164.  Generic atomic storage, writer identity, and
recovery are defined separately by `STATE_CONCURRENCY.md`,
`STATE_RECOVERY.md`, and #101.

## 1. Scope and authority

Issue lifecycle is durable repository state.

It records workflow transitions that must survive loss of a clone, worktree,
workspace, branch, or local current-work pointer.  Clone-local and
worktree-local records may point at this state but cannot replace or advance it.

Repository-host issue state is provider input.  It does not silently overwrite
RWF lifecycle history.  Transitions that synchronize host and RWF state must do
so through their owning workflow operation.

## 2. Schema version and record identity

The initial lifecycle value schema version is `1`.

There is one logical lifecycle record per issue.  Its canonical record key is:

```text
issues/<issue-number>/lifecycle
```

Issue numbers are positive decimal integers represented without leading zeroes.

The lifecycle value is stored inside the generic #101 record envelope.  The
generic envelope owns record revision, previous revision, writer identity, and
session identity.  This schema does not duplicate those fields.

## 3. Lifecycle value

A lifecycle value has this shape:

```json
{
  "schema_version": 1,
  "issue": "64",
  "state": "active",
  "dependency_satisfied": false,
  "relationship_revision": 7,
  "history": [
    {
      "sequence": 0,
      "transition": "start",
      "from": "unstarted",
      "to": "active",
      "candidate": "v0.1.40-issue.64.0.0"
    }
  ]
}
```

Every lifecycle value contains exactly:

- `schema_version`;
- `issue`;
- `state`;
- `dependency_satisfied`;
- `relationship_revision`;
- `history`.

`relationship_revision` is the canonical relationship-graph revision consumed
by the lifecycle transition, or `null` when the transition does not consume
relationship state.

## 4. Lifecycle states

The initial states are:

- `unstarted` -- no successful start transition has occurred;
- `active` -- issue work has been started or re-entered;
- `aborted` -- active work was explicitly abandoned without completion;
- `accepted` -- all required acceptance/validation for the exact task
  candidate has succeeded, but durable completion has not occurred;
- `completed` -- the issue's required workflow outcome is durably complete.

`accepted` and `completed` are deliberately distinct.  Acceptance does not
itself imply merge authorization or final integration.

`completed` is terminal for issue-work readiness.  Other terminal lifecycle
states may be introduced only by a later schema version or explicit contract
extension.

## 5. Dependency satisfaction

A direct issue dependency is satisfied only when the dependency's canonical
durable lifecycle value has:

```text
state == "completed"
dependency_satisfied == true
```

The Boolean is explicit so readiness consumers do not infer dependency
semantics from a state-name string.  In schema version 1 it must be `true`
exactly for `completed` and `false` for every other state.

In particular:

- `accepted` does not satisfy a dependency;
- `aborted` does not satisfy a dependency;
- a closed repository-host issue does not satisfy a dependency by itself;
- a local workspace marked complete does not satisfy a dependency by itself.

This gives #164 one normalized fact to expose and #144 one durable fact to
consume.

## 6. History

`history` is an append-only semantic transition history.

Every entry contains exactly:

- `sequence` -- zero-based monotonically increasing integer;
- `transition` -- semantic transition name;
- `from` -- prior lifecycle state;
- `to` -- successor lifecycle state;
- `candidate` -- exact task/candidate identity consumed by the transition, or
  `null` when no candidate exists.

The first entry has sequence `0`.  Each later entry increments by one.

A replacement of the generic record may append one semantic lifecycle
transition.  It must not delete, reorder, rewrite, or silently compact prior
history.

Generic writer/session provenance remains in the #101 record envelope.  A
future need for per-history-entry durable provenance requires an explicit schema
extension rather than copying transient process identity into this value.

## 7. Legal semantic transitions

Schema version 1 permits:

```text
unstarted -> active     start
active    -> aborted    abort
aborted   -> active     re-enter
active    -> accepted   accept
accepted  -> active     reject/reopen
accepted  -> completed  complete
```

A transition not listed here fails closed.

A failed validation attempt that leaves issue lifecycle state `active` belongs
to validation/audit evidence and task-version history; it does not create a
same-state lifecycle event merely to record activity.

Completion is distinct from acceptance because integration/authorization policy
can remain between those facts.

## 8. Relationship reference

A lifecycle transition that consumes canonical issue relationships records the
exact generic record revision in `relationship_revision`.

This reference does not copy relationship fields into lifecycle state.

If the relationship graph advances later, historical lifecycle state remains
interpretable against the relationship revision it consumed.  A caller deciding
whether a new transition is legal must use current authoritative relationship
state when that transition's contract requires it.

## 9. Reconstruction and recovery

Durable lifecycle history must remain reconstructable after local branch,
workspace, or clone cleanup.

Recovery may derive a local current-work pointer from lifecycle state only when
the complete recovery contract proves one unique local projection.  It must not
recreate worker ownership, session identity, or an active local claim merely
because the durable issue is `active`.

A malformed or unsupported lifecycle record is not equivalent to `unstarted`.
It fails closed.

Absence of a lifecycle record may project to `unstarted` only when the
canonical lifecycle reader can establish that no durable lifecycle record has
ever existed for that issue.  A missing record that should exist is a recovery
error, not a reset.

## 10. Concurrency

Lifecycle mutation uses the generic #101 compare-and-swap revision.

A transition is evaluated from one exact lifecycle revision and any other
declared authoritative inputs.  Stale lifecycle or relationship input is a
conflict requiring reread and semantic recomputation, not last-writer-wins.

A workflow transition spanning lifecycle plus other durable records must obey
the multi-record transaction/recovery contract before exposing partial success.

## 11. Provider and local-state separation

The lifecycle value contains no GitHub-specific payload.

Repository-host open/closed state, labels, PR state, and similar provider facts
must enter through provider-neutral adapters and owning transitions.

The lifecycle value also contains no:

- workspace ID;
- worktree path;
- local branch-selection pointer;
- worker ID beyond generic mutation provenance;
- session ownership;
- clone-local claim.

Those facts belong to their declared local or provider scopes.

## 12. Validation requirements

Implementations of this schema must prove at least:

1. all legal transitions reconstruct losslessly;
2. illegal transitions fail closed;
3. history is append-only and sequence-contiguous;
4. abort preserves all prior history;
5. re-entry appends rather than replacing the aborted generation;
6. accepted and completed remain distinct;
7. dependency satisfaction is true exactly for completed;
8. local workspace/current-work state cannot satisfy a dependency;
9. malformed and unsupported values fail closed;
10. stale CAS input cannot overwrite newer lifecycle state;
11. relationship revisions round-trip without copying relationship semantics;
12. branch/workspace cleanup cannot erase durable lifecycle history.

## 13. Consumer contract

#164 owns persistence and the normalized lifecycle reader.

Known consumers include:

- #64 for start/re-entry;
- #98 for abort;
- #144 for dependency/readiness classification;
- #72 for canonical read-only workflow projection.

The preliminary synchronization method in #163 requires those consumers to be
checked against this contract before #164 implementation begins.
