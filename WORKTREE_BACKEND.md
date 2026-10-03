# Git Worktree Workspace Backend Contract

Status: authoritative Git-facing contract for repository-local RWF workspace
provisioning and retirement.

This document defines how the local workspace abstraction is materialized with
Git branches and worktrees.  It is subordinate to
[WORKSPACE_MODEL.md](WORKSPACE_MODEL.md): Git mechanics must implement the
workspace semantics without becoming the semantic authority.

## 1. Purpose

The backend provides isolated filesystem/Git contexts so multiple workers can
operate on independent issues concurrently in one repository.

The backend owns:

- branch/worktree provisioning;
- deterministic path and identity checks;
- safe reuse detection;
- partial-failure rollback;
- dirty-work protection;
- worktree retirement/pruning;
- stale/orphan recovery diagnostics.

It does not own:

- issue readiness;
- issue lifecycle/history;
- dependency semantics;
- workspace claim ownership;
- validation evidence;
- integration authorization.

## 2. Inputs

Provisioning receives normalized semantic inputs:

```text
workspace_id
issue_number
base_ref
base_sha
branch_name
worktree_path
```

The caller must resolve semantic issue/base policy before invoking the backend.

The backend verifies Git facts but does not infer semantic dependencies from
branch ancestry.

## 3. Base identity

Provisioning is bound to an exact base SHA.

A symbolic base such as `main` may be supplied for diagnostics, but the
backend records and verifies the exact resolved commit used to create the
workspace.

If the symbolic base moves between planning and mutation, the backend must
either:

- reject the stale plan; or
- require the caller to re-plan explicitly.

It must not silently create the worktree from a different commit.

## 4. Branch identity

Each workspace uses a deterministic issue branch name supplied by the semantic
workflow layer.

The backend must reject:

- a branch already checked out by an unrelated worktree;
- an existing branch whose verified ownership/base is incompatible with the
  requested workspace;
- ambiguous reuse where the backend cannot prove the branch belongs to the
  requested workspace.

The backend may reuse an existing compatible branch only when the caller
explicitly requests reuse and all ownership/base checks pass.

## 5. Worktree path

The worktree path is deterministic for a given local workspace unless the
caller explicitly selects another path before creation.

The backend must reject a path that:

- already contains unrelated files;
- is registered to another Git worktree;
- resolves inside a location forbidden by repository policy;
- aliases another workspace path after normalization.

Path comparison must use platform-appropriate canonicalization.

## 6. Provision transaction

Provisioning is a transaction with these logical stages:

```text
validate plan
  -> reserve/check branch identity
  -> create branch if required
  -> add worktree
  -> verify worktree HEAD/branch/path
  -> report success
```

Success requires all postconditions.

If any stage fails, rollback removes only resources created by this attempt.

Pre-existing compatible resources must never be deleted during rollback.

## 7. Provision postconditions

On success:

- the worktree exists at the requested canonical path;
- its HEAD is the expected branch/candidate;
- the branch identity matches the requested workspace;
- the initial commit/base relation is exactly the planned one;
- the primary checkout and other worktrees are unchanged;
- no workspace-local metadata was committed accidentally.

The backend returns normalized facts sufficient for the workspace store to
record the materialized context.

## 8. Failure atomicity

A failed provision operation must not report success.

Rollback rules:

- if this attempt created a worktree, remove that worktree registration/path
  when safe;
- if this attempt created a branch and no durable work was produced, remove the
  branch when safe;
- never remove a branch/worktree that pre-dated the attempt;
- never delete untracked/uncommitted files to make rollback succeed;
- if automatic rollback cannot safely complete, return an explicit recoverable
  partial state describing exactly what remains.

Silent orphan creation is forbidden.

## 9. Existing worktree detection

Before mutation, enumerate Git's registered worktrees and normalize:

- path;
- HEAD;
- branch/ref;
- detached state;
- prunable/stale state where reported.

Do not rely solely on directory existence.

An existing registered worktree is reusable only when it is proven to be the
same workspace context.

## 10. Dirty-work protection

Retirement and rollback must inspect the target worktree for protected work.

At minimum, protected work includes:

- modified tracked files;
- staged changes;
- untracked files;
- unresolved merge/rebase/cherry-pick state;
- commits that would become unreachable by the requested cleanup when no
  durable reference preserves them.

A normal cleanup operation must stop rather than discard protected work.

No automatic `git reset --hard`, `git clean -fd`, or equivalent destructive
fallback is permitted.

## 11. Retirement transaction

Retirement proceeds:

```text
verify workspace ownership
  -> verify lifecycle permits retirement
  -> verify no protected local work
  -> verify required durable references/history
  -> remove worktree
  -> prune stale worktree metadata
  -> optionally delete disposable branch
  -> verify retirement
```

Branch deletion is a separate explicit policy decision.

Closing a workspace does not inherently mean its issue branch should be
deleted.

## 12. Branch deletion safety

A branch may be deleted only when the caller's policy authorizes it and the
backend proves deletion will not lose required work.

A branch is not disposable merely because:

- its worktree is clean;
- a PR exists;
- another branch contains similar changes;
- a workspace is COMPLETE or ABORTED.

The backend must use exact Git reachability facts required by the caller's
cleanup policy.

## 13. Stale/orphan worktrees

The backend must distinguish:

- registered and healthy;
- registered but missing path;
- path exists but Git registration is absent;
- prunable Git metadata;
- branch exists without workspace/worktree;
- workspace metadata references a missing worktree.

Recovery must be diagnostic first.

The initial implementation may require explicit cleanup/recovery rather than
auto-repair when ownership is ambiguous.

## 14. Concurrency

Two workers may provision different workspaces concurrently.

The backend must tolerate independent worktree creation without using a single
shared literal temporary branch/ref.

Two workers attempting to provision the same branch/path must result in at most
one successful owner.

Git's own locking/errors are useful evidence but do not replace workspace CAS
claim semantics.

## 15. Platform requirements

The backend must work with standard Git worktree behaviour on supported Linux
and Windows environments.

Tests must cover:

- path normalization;
- spaces in paths;
- branch names;
- worktree enumeration;
- removal/prune behaviour;
- dirty-state detection.

Shell-specific quoting must remain below the semantic interface.

## 16. No remote/provider dependency

Provisioning and retirement are local Git operations.

The backend must not require:

- GitHub API access;
- hosted CI;
- WorkStack;
- remote branch creation.

Remote publication remains a separate workflow responsibility.

## 17. Recovery records

When a mutation cannot roll back fully, return a structured recovery result
containing at least:

```text
workspace_id
operation
completed_stages
remaining_resources
protected_work_detected
recommended_next_action
```

The recovery result must not claim that cleanup occurred when it did not.

## 18. Integration tests

Production-shaped tests must use disposable real Git repositories and actual
`git worktree` commands.

Required cases include:

1. provision one workspace from an exact base;
2. provision multiple independent workspaces;
3. reject branch collision;
4. reject path collision;
5. reject stale planned base;
6. inject failure after branch creation and prove safe rollback;
7. refuse retirement with modified tracked files;
8. refuse retirement with untracked files;
9. retire a clean worktree;
10. preserve a non-disposable branch;
11. detect stale/prunable worktree metadata;
12. prove one workspace cleanup cannot remove another workspace.

Mocks may supplement these tests but cannot replace the real-Git suite.
