# RWF State Ownership and Layout

Status: authoritative ownership/layout contract for `.repoworkflow` state.

This document defines where RWF state belongs and which scope is authoritative.
It separates durable repository facts from clone-local coordination and
worktree-local execution context.

## 1. Three storage scopes

RWF uses three distinct scopes.

### 1.1 Durable repository state

Durable/shared workflow facts live in the repository-controlled
`.repoworkflow/` tree and are versioned with repository history.

Examples include:

- canonical relationship graph records;
- durable issue lifecycle/history;
- validation/audit evidence that must survive clone deletion;
- authorization/integration records that are repository facts.

Durable state may be shared across clones through normal repository history.

### 1.2 Clone-common local state

Local coordination that must be visible to every worktree in one clone lives
under the clone's Git common directory:

```text
<git-common-dir>/repoworkflow/
```

Examples include:

- workspace registry;
- workspace claim records and CAS revisions;
- clone-wide local locks/coordination records;
- mappings from workspace IDs to worktree paths.

This state is local to one clone and must never be committed.

Git worktrees share the same clone-common namespace so two worktrees cannot
independently claim the same local workspace.

### 1.3 Worktree-local state

Execution/navigation state belonging to one worktree lives under that
worktree's Git directory:

```text
<git-dir>/repoworkflow/
```

Examples include:

- this worktree's current issue/context;
- transient navigation/resume pointers;
- worktree-local caches;
- state meaningful only to the current isolated checkout.

Each linked worktree therefore has its own worktree-local namespace while
sharing clone-common coordination state.

The semantic current-work/re-entry record is defined in
[CURRENT_WORK_STATE.md](CURRENT_WORK_STATE.md).  Its persistent semantic
store/reader is owned by #172.

## 2. Git path resolution

Implementations must derive paths from Git rather than assuming that
`.git` is a directory.

Use Git-equivalent facts for:

- repository root;
- worktree Git directory;
- Git common directory.

Linked worktrees commonly have a `.git` file that points into the main
repository's Git metadata.  Code must handle that case correctly.

Path resolution must work on supported Linux and Windows environments.

## 3. Authority rules

A state category has exactly one authoritative scope.

A caller must not:

- treat clone-common state as durable repository truth;
- reconstruct durable history from a local claim;
- place clone-wide claims in a worktree-local namespace;
- commit local workspace/session identity into repository history;
- use durable repository files as mutable local lock files.

When durable and local records reference the same issue, durable facts win for
workflow history and local facts win only for local execution ownership.

## 4. Workspace placement

The workspace subsystem uses both local scopes.

Clone-common:

```text
<git-common-dir>/repoworkflow/workspaces/
  <workspace-id>/
    claim.json
    workspace.json
```

Worktree-local:

```text
<git-dir>/repoworkflow/
  current-workspace.json
  resume.json
```

The exact file set may grow, but the ownership boundary is fixed.

A workspace claim must be clone-common because all worktrees in the clone must
observe the same revision and owner.

A worktree resume pointer may be worktree-local because it belongs only to that
checkout.

## 5. Durable relationship placement

The canonical relationship graph is durable repository state.

Its eventual persisted representation belongs under committed
`.repoworkflow/`, not under Git-local metadata.

The pure schema/model is defined in
[RELATIONSHIP_GRAPH.md](RELATIONSHIP_GRAPH.md).

The persistent graph store/reader is owned by #145.

## 5.1 Durable lifecycle placement

Canonical issue lifecycle/history is durable repository state.

Its semantic value and transition invariants are defined in
[ISSUE_LIFECYCLE_STATE.md](ISSUE_LIFECYCLE_STATE.md).  The canonical persistent
store/reader is owned by #164.

Lifecycle truth must not be reconstructed from clone-local current-work or
workspace records.

## 6. Atomicity boundary

Durable mutation concurrency and writer identity are defined by
[STATE_CONCURRENCY.md](STATE_CONCURRENCY.md).

Moving state between scopes is not an implicit side effect.

A workflow transition that updates both durable and local facts must define:

1. which durable mutation is authoritative;
2. which local projection/reference follows it;
3. rollback/recovery behaviour when only one side succeeds.

Local convenience state must never cause a failed durable mutation to appear
successful.

## 7. Clone deletion and portability

Deleting one clone may destroy clone-common and worktree-local state.

That is acceptable only for facts classified as local.

Any fact required to reconstruct repository workflow correctness after clone
loss must therefore be durable.

Conversely, recreating a clone must not require recovery of old local claims or
session IDs from repository history.

## 8. Multi-worktree invariants

With multiple worktrees:

- all worktrees share one clone-common workspace claim namespace;
- each worktree has independent current-context/resume state;
- one worktree cannot overwrite another's worktree-local state;
- a claim made from one worktree is immediately authoritative for all
  worktrees in that clone;
- no worktree path or branch ancestry implies issue dependency.

## 9. Multi-clone invariants

Clone-common claims coordinate only workers sharing one clone.

They are not a distributed lock across independent clones or machines.

Cross-clone workflow safety relies on durable repository facts, candidate
identity, server/integration controls, and other explicit shared mechanisms.

RWF must not falsely present a clone-local workspace claim as global exclusion.

## 10. Local-only initialization

`rwf init local-only` may keep the entire RWF footprint local.

In that mode, repository-wide durable adoption is intentionally absent.

Local-only state must still preserve the same internal ownership separation:

- clone-common coordination;
- worktree-local context;
- locally materialized workflow facts where the mode requires them.

Local-only data should be excluded through Git-local mechanisms such as
`.git/info/exclude` rather than by mutating project `.gitignore` solely for
local use.

## 11. Migration from existing local cache

Existing RWF local cache files under a worktree Git directory remain
worktree-local unless explicitly migrated.

A future migration must not silently reinterpret an old worktree-local cache as
clone-common authoritative claim state.

Workspace implementation begins with the new scoped layout rather than reusing
an ambiguous existing cache file.

## 12. Testing requirements

Implementations consuming this contract must test:

1. normal checkout path resolution;
2. linked-worktree path resolution;
3. two worktrees observe the same clone-common claim record;
4. two worktrees keep distinct worktree-local current context;
5. local files do not appear in repository status/commits;
6. clone-common state is not mistaken for durable state;
7. deleting local state cannot erase durable workflow history;
8. Linux and Windows path behaviour.

The workspace store in #138 may depend directly on this ownership/layout
contract without waiting for the complete durable state-store chain.
