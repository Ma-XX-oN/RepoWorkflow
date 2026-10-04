# Parent Branch Workflow

Status: authoritative parent-identity and recovery contract.

Tracking issues: #225, #227.

## 1. Purpose

Every RWF work branch has exactly one semantic parent branch.  The branch is
created from that parent and successful completion integrates back into that
same parent.

The parent relationship is independent of issue dependency, umbrella ownership,
and shared-umbrella attachment.  None of those relationships may create or
change parent topology.

Git has no built-in "parent branch" property.  Current ref ancestry alone is
insufficient to recover branch identity deterministically after parents advance,
siblings are created, or several refs point at the same commit.  RWF therefore
records parent identity once in ordinary Git history and validates it against
Git topology when recovering it.

## 2. Parent identity marker

The first commit created specifically for an RWF work branch is an empty
structured identity commit.  Its first parent is the exact parent tip from which
the work branch was created.

Its commit message contains exactly one structured trailer:

```text
RWF-Parent: <canonical-branch-name>
```

`<canonical-branch-name>` is the normalized branch name without a ref prefix,
for example `main` or `lane-200-umbrella-title`.  It is not an arbitrary ref
name and is never a remote-tracking name such as `origin/main`.

The identity commit is permanent logical branch history.  Pause checkpoints are
separate temporary commits and do not replace or modify the identity marker.

The marker records one fact once.  There is no independently mutable completion
or integration target.

## 3. Creation rule

When RWF first creates work branch `W` from current branch `P`:

1. require `P` to be an unambiguous canonical local branch identity;
2. resolve and retain the exact commit `P0` at the parent tip;
3. create `W` at `P0`;
4. create one empty parent-identity commit on `W` whose first parent is `P0`
   and whose sole `RWF-Parent` trailer names `P`;
5. continue normal work from that identity commit.

If the current checkout is detached, the parent branch name is ambiguous, the
marker cannot be created, or any creation step cannot be completed
recoverably, work-branch creation fails closed.

The creation marker does not create an issue dependency or umbrella
relationship.

## 4. Deterministic recovery

Given work branch `W`, recovery is a validation operation, not a search for the
"closest" current branch.

### 4.1 Locate identity evidence

Walk `W`'s first-parent history and collect commits containing a valid
`RWF-Parent` trailer that claim parent identity for `W`.

Recovery succeeds only when exactly one applicable identity marker exists.
Missing, malformed, or conflicting markers fail closed.

Later branch points, merges, descendants, and sibling branches are not
candidates for replacing this marker.

### 4.2 Resolve the recorded parent name

For recorded canonical parent name `P`, collect only refs that represent that
same branch name:

- `refs/heads/P`;
- fetched remote-tracking refs `refs/remotes/<remote>/P`.

Do not inspect unrelated ref names to choose a parent.  Sort all inspected full
ref names lexically before validation so behaviour never depends on Git ref
enumeration order.

A local and one or more remote-tracking refs with the same canonical branch
name are representations of the same semantic parent, not competing parent
identities.

At least one representation of `P` must exist locally in the Git object/ref
database.  Recovery performs no network operation.

### 4.3 Validate topology

Let `P0` be the first parent of the identity commit.

Every accepted current representation of `P` must contain `P0` in its
ancestry or equal `P0`.  A representation that moved to unrelated history is
invalid evidence and makes recovery fail closed.

The work branch must still contain its identity commit.  Rewriting the branch so
that the marker disappears makes parent recovery fail closed.

If these checks pass, the recovered semantic parent is canonical branch name
`P`.

## 5. Required cases

### main -> issue

An issue branch created from `main` records `RWF-Parent: main`.  Advancement
of `main` after creation does not change the recovered parent.

### main -> lane -> issue

A lane created from `main` records `main`.  An issue created from that lane
records the lane's canonical branch name.  The issue does not recover `main`
merely because `main` is also an ancestor.

### Siblings

Sibling work branches each retain their own identity marker.  Creating,
advancing, merging, or deleting one sibling cannot change another sibling's
recorded parent.

### Equal-tip refs

If unrelated branch names point at the same commit as the recorded parent, they
are ignored.  Equal commit identity is not branch identity.

### Parent advancement

The recorded parent may advance normally.  Recovery validates that the creation
tip remains in the parent's ancestry; it does not require the parent still to
point at the creation commit.

### Fetched clone

Because the marker is ordinary commit history, fetching the work branch carries
the identity evidence.  A fetched remote-tracking ref for the recorded parent is
sufficient when its topology validates, even if no local parent branch exists.

### Deleted local parent ref

Deletion of `refs/heads/P` does not prevent recovery when a valid fetched
`refs/remotes/<remote>/P` remains.  If no representation of `P` remains,
recovery fails closed rather than guessing another ancestor ref.

### Nested work branches

Each nested work branch records its immediate creation parent.  Recovery never
skips an intermediate lane/work branch in favour of an older ancestor.

### Ambiguous or corrupt state

Conflicting identity markers, malformed parent names, unrelated rewritten parent
refs, missing parent representations, or missing identity history all fail
closed.  No lexical, timestamp, ancestry-distance, default-branch, umbrella, or
dependency tie-breaker is permitted.

## 6. Legacy migration boundary

Legacy relationship records may contain independent `branch_base` and
`integration_target` fields.

If the fields are equal, that common value is the legacy parent candidate.

If they differ, neither field wins.  Migration must apply this contract's
Git-native recovery to the corresponding work branch.  Migration succeeds only
when exactly one parent is recovered.  Otherwise it fails closed and preserves
the prior durable relationship state.

A legacy record with no legal parent is accepted only where the relationship
schema explicitly permits a root/null parent.  Null is never inferred merely
because recovery failed.

## 7. Invariants

- A work branch has exactly one semantic parent.
- Creation parent and completion/integration target are the same relationship.
- Parent identity is recorded once and is not independently mutable.
- Dependency topology never implies parent topology.
- Parent topology never creates dependency edges.
- Recovery never depends on Git ref enumeration order.
- Siblings and later descendants cannot replace the recorded parent.
- Recovery uses local Git state only and performs no implicit network access.
- Ambiguous, missing, conflicting, or topologically invalid evidence fails
  closed.
- Normal push/fetch preserves the identity evidence.
- Failed legacy migration preserves the prior valid durable state.

## 8. Consumer contract

The single-parent relationship schema stores one `parent` concept.  New work
branch creation materializes that concept as the identity marker defined here.
Readers and lifecycle operations consume the same parent identity; no
authoritative path may maintain a second independently configurable integration
target.

`done` must recover and validate this parent before integration.  It must not
select a target from dependency edges, umbrella ownership, current checkout,
default branch, or nearest ancestry.

## 9. Verification matrix

Implementations of this contract must test:

1. `main -> issue`;
2. `main -> lane -> issue`;
3. multiple siblings;
4. parent advancement;
5. unrelated equal-tip refs;
6. nested work branches;
7. fetched work/parent remote-tracking refs in another clone;
8. deleted local parent ref with a valid fetched remote representation;
9. missing parent representation;
10. conflicting/malformed identity markers;
11. rewritten parent history that no longer contains the creation tip;
12. ref enumeration in different orders producing the same result; and
13. dependency/umbrella changes leaving parent identity unchanged.
