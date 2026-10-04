# Parent-Branch Work Lifecycle

Status: proposed authoritative replacement contract tracked by #225.

This document records the target Git-native work lifecycle.  Existing
relationship, issue-start, and workspace contracts remain authoritative until
the #225 migration is implemented and validated.  Do not mix old and new
semantics partially.

## 1. Single parent invariant

Every RWF work branch has exactly one parent branch.

A work branch is created from its parent and successful completion integrates
back into that same parent.  There are not two independently configurable facts
named `branch_base` and `integration_target`; both are the one `parent`
relationship.

For example:

```text
main
└── lane-200-umbrella-title
    ├── issue-201-first-child
    ├── issue-202-second-child
    └── issue-203-third-child
```

Each issue completes into the lane.  The lane completes into `main`.

Git topology represents the integration hierarchy.  Dependency topology remains
separate: dependency edges control readiness/order and do not implicitly change
the parent branch.

## 2. Start

The target commands are:

```text
rwf start <issue#> [addendum]
rwf start lane <umbrella-issue#> [addendum]
```

`start` means start-or-resume.

On first start, RWF:

1. reads the issue title from locally synchronized issue metadata;
2. derives the canonical branch name;
3. creates the branch from the current parent branch;
4. switches to it; and
5. establishes active lifecycle state.

On a later start, RWF finds the existing derived branch, switches to it, and
recovers its existing state.  If the branch is paused, start resumes it.

Normal branch names are:

```text
issue-123-ticket-title
lane-200-umbrella-ticket-title
```

The optional addendum is simply extra text appended after the normalized issue
title:

```text
issue-123-ticket-title-alternative
lane-200-umbrella-ticket-title-experimental
```

The addendum has no workflow semantics.  It only appends user-supplied text to
the branch name.

## 3. Network boundary

`start` does not implicitly contact the network.

Ordinary Git synchronization remains ordinary Git.  A developer who wants the
current remote Git state can use `git pull` before starting.  RWF does not add a
wrapper merely to rename that Git operation.

RWF's dependency/ticket synchronization operation has a different
responsibility: it must synchronize issue titles as well as dependency
relationships for every issue represented in the local graph.

After successful synchronization, ordinary workflow operations use local data.
At minimum, start, pause, abort, done, branch-name derivation, parent discovery,
and local dependency analysis do not require network access.

Starting an issue whose title is unavailable locally fails explicitly rather
than silently querying the ticket server.

## 4. Shared branch convergence

One logical lane has one canonical lane branch.  Multiple workers may converge
onto it.

If another worker advances a shared remote branch first, a non-fast-forward
push is a normal concurrency condition.  The later worker fetches, integrates
the new tip, reverifies, and retries.  Non-overlapping changes may integrate
automatically; actual conflicts require resolution.

Normal shared-branch recovery never force-pushes.

## 5. Lifecycle

The target user-facing lifecycle vocabulary is:

```text
start
pause
abort
done
```

`start` includes resume.

`pause` preserves accumulated state without abandoning the attempt.

`abort` abandons the attempt according to its recovery/cleanup contract.

`done` verifies and integrates the work into its parent branch.

## 6. Portable pause checkpoint

`rwf pause` creates a temporary structured RWF pause commit at the work branch
tip.

A minimal marker may be:

```text
RWF-Pause: 1
```

The marker does not need an issue number because branch identity supplies it.
It does not need a dirty flag: an empty checkpoint is clean and a changed
checkpoint is dirty.

Pause emulates Git stash preservation semantics while placing the checkpoint in
ordinary branch history so it can be pushed, fetched, and resumed in another
clone.

Supported inclusion switches mirror Git stash:

```text
rwf pause
rwf pause -u
rwf pause --include-untracked
rwf pause -a
rwf pause --all
```

Semantics:

- plain pause preserves tracked staged and unstaged changes;
- `-u` / `--include-untracked` additionally preserves untracked files;
- `-a` / `--all` additionally preserves ignored files.

The checkpoint representation must preserve staged versus unstaged state.

Pause creates exactly one new commit.  For a clean worktree, that commit is an
empty marker commit.  Otherwise, that same commit contains all information
needed to reconstruct the selected paused state.  No auxiliary pause commits
are created.

## 7. Resume

When start encounters an RWF pause checkpoint at the branch tip, it restores
the checkpointed index/worktree state and resets the temporary pause checkpoint
off the logical development history.

Conceptually:

```text
A──B──P
      ^
     HEAD
```

becomes:

```text
A──B
   ^
  HEAD

+ restored staged/unstaged working state
```

A successful resume therefore returns the developer to the pre-pause
development HEAD with the saved work restored.

Pause/resume failure must leave recoverable state and must not silently discard
anything covered by the selected inclusion semantics.

## 8. Migration

The current authoritative relationship schema stores `branch_base` and
`integration_target` independently.  The current issue-start/workspace model
also separates canonical issue activation from workspace provisioning.

Those contracts must not be partially rewritten before migration is ready.
#225 owns decomposition of the implementation/migration work.

The completed migration must:

- replace independent branch-base/integration-target configuration with one
  parent invariant;
- provide start/start-lane branch creation and resume;
- synchronize issue titles with dependency/ticket metadata for offline use;
- implement portable stash-compatible pause checkpoints;
- make done integrate only into the parent;
- define shared-lane convergence and reverification; and
- update command grammar, documentation, tests, and existing durable-state
  migration together.

## 9. Core invariants

1. Creation parent and completion target are the same parent.
2. Dependency topology and integration topology remain independent.
3. Normal workflow operations do not silently require network access.
4. Existing work branches resume rather than being reinterpreted as new work.
5. Pause preserves all state covered by its selected stash-compatible options.
6. Successful resume removes the temporary pause marker from logical history.
7. Failed pause/resume/integration leaves a recoverable prior state.
8. Shared-branch concurrency is resolved by integration and reverification, not
   normal force-push.


## 10. Implementation decomposition

Tracked by #225:

```text
#227 parent identity/recovery contract
  └─→ #228 single-parent relationship migration
        └─→ #230 canonical start-or-resume ←─ #229 offline title metadata
              ├─→ #231 portable pause checkpoint ─→ #232 resume restoration
              ├───────────────────────────────→ #233 parent-directed done
              └───────────────────────────────→ #234 abort/workspace alignment

#230 + #231 + #232 + #233 + #234 ─→ #235 grammar/docs migration

#78 + #120 + #145 ─→ #229 ─→ #214 dependency-sync CLI
#64 ────────────────────────→ #230
#98 + #138 + #142 ─────────→ #234
```

The decomposition deliberately freezes parent recovery before schema migration.
Git stores commit ancestry and refs but no permanent “parent branch” property,
so recovery must be deterministic and must fail closed when topology is truly
ambiguous.

Portable pause has one fixed topology rule: pause creates exactly one new commit
at the branch tip.  That commit contains whatever encoding is required to
reconstruct staged and unstaged state.  It must not create auxiliary pause
commits.

Branch resume identity is stable by issue number plus optional addendum.  The
issue title contributes the human-readable branch name at creation time, but a
later ticket-title change does not rename or orphan an existing work branch.

Old records whose `branch_base` and `integration_target` differ are not resolved
by arbitrarily preferring either field.  Migration applies the frozen parent
recovery rule and succeeds only when one parent is unambiguous.


### Addendum semantics

The optional addendum is branch-name text only.  It is not a workflow marker
and must not affect convergence, dependencies, lifecycle, or attempt type.

### One-commit pause invariant

Every successful `rwf pause` creates exactly one new commit.  A clean pause uses
an empty marker commit.  A non-clean pause uses that same commit to store all
information needed to reconstruct the selected paused state, including staged
versus unstaged state.  No auxiliary pause commits are permitted.

## 11. Published implementation lanes

These are the repository-visible parallel-work allocations for #225.

### Lane A — parent topology

```text
A.227 → A.228
```

Freeze deterministic parent recovery, then migrate the relationship graph to the
single-parent topology.

Completion at publication: **0/2 = 0%**.

### Lane B — offline ticket metadata

```text
B.229
```

Persist synchronized issue titles for offline workflow operation.  #229 also
feeds #214 dependency synchronization.

Completion at publication: **0/1 = 0%**.

### Convergence

```text
Lane A (A.227 → A.228) + Lane B (B.229) + #64
    ↓
#230 start/start-lane
    ├→ #231 one-commit pause → #232 resume
    └→ #233 parent-directed done

#230 + #232 + #98/#138/#142 → #234
#230 + #231 + #232 + #233 + #234 → #235 → #225 complete
```

Lane assignments are coordination metadata, not replacement dependency truth.
Workers must re-check issue blockers before advancing.  Lane A and Lane B may run
concurrently.  Completion percentages are closed lane issues divided by total
lane issues and must be recomputed when status changes.
