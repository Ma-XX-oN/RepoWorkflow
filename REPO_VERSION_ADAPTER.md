# Repository Version Adapter Contract

Status: authoritative contract for issue #89.

This document defines the repository-owned `repo-version` boundary consumed by
RepoWorkflow.  Core RWF owns version lifecycle semantics.  A consumer adapter
owns where and how its literal version is stored.

## 1. Configuration and invocation

`.ci/repoworkflow.json` supplies `versionCommand` as a non-empty argv array.
RWF invokes that command from the repository root and appends exactly one of the
semantic requests defined below.

The adapter must not require shell interpretation.  Arguments are passed as
argv elements.

## 2. Canonical read

An invocation with no additional arguments is read-only.

On success it must:

- exit zero;
- write exactly one non-empty line to stdout;
- report either a stable `X.Y.Z` version or a development
  `X.Y.Z-issue.P.Q.R` version; and
- leave the worktree, index, candidate history, symbolic `HEAD`, and local Git
  refs unchanged.

All numeric components are non-negative decimal integers.  RWF treats the
reported value as canonical repository version state.

## 3. Semantic mutation requests

The complete schema-1 mutation vocabulary is:

```text
task --issue N
task --increment CI-iteration
task --increment merge-integration-failed
integrate --increment patch
integrate --increment minor
release-major
```

`N` is a positive decimal issue number.

The adapter derives and applies the literal successor.  Core RWF must not know
the consumer's version file, manifest, source constant, generator, or other
storage mechanism.

Successful transitions have these semantic effects:

- `task --issue N`: stable `X.Y.Z` becomes
  `X.Y.Z-issue.N.0.1`;
- `task --increment CI-iteration`: development `R` increments by one while
  `X.Y.Z`, `P`, and `Q` remain unchanged;
- `task --increment merge-integration-failed`: development `Q` increments
  by one, `R` resets to one, and `X.Y.Z` and `P` remain unchanged;
- `integrate --increment patch`: stable patch increments by one;
- `integrate --increment minor`: stable minor increments by one and patch
  resets to zero;
- `release-major`: stable major increments by one and minor/patch reset to
  zero.

A request in the wrong source namespace is invalid and must fail rather than
guessing or repairing the state.

## 4. Mutation postconditions

A successful mutation may change only repository-owned version-bearing
worktree/index state required to represent the requested successor.

It must not:

- create a commit;
- move or detach `HEAD`;
- create, move, or delete a local Git ref;
- change unrelated repository state; or
- perform another lifecycle transition as a side effect.

After a zero exit, RWF re-reads the canonical version and verifies that the
observed before/after relation is exactly the requested semantic transition.
A zero exit with an inconsistent successor is an adapter contract violation.

## 5. Failure and transaction boundary

Adapter mutation is failure-atomic at the adapter boundary.  If the adapter
exits non-zero, it must restore every version-storage change it attempted before
returning.  RWF reports the failure and does not infer a successor.

RWF snapshots Git identity/ref invariants around every adapter invocation.  It
rejects forbidden history, `HEAD`, or ref mutation.

A successful adapter mutation is not itself committed.  The calling RWF
transition owns the wider repository transaction.  If a later step fails, that
caller restores the complete pre-transition repository state.  This separation
lets callers such as candidate preparation roll back version changes together
with their own bookkeeping without teaching the adapter about RWF state.

## 6. Normalized RWF result

The RWF invocation layer exposes canonical version strings, not adapter stdout
or repository storage details.

A mutation result contains the canonical version observed before the request
and the canonical version observed after it.  Callers use the normalized
successor and can retain the predecessor as transaction evidence.

Adapter stderr/stdout diagnostics are surfaced on failure but are not parsed as
workflow state.

## 7. Consumer synchronization

The preliminary #163 dependency-contract synchronization pass checked the
direct #118 implementation consumer and the known direct consumers of #118:
#64, #82, #87, #102, #86, #105, #106, and #109.

Their required operations are covered by this contract:

- issue start uses `task --issue N`;
- verification iteration uses `task --increment CI-iteration`;
- integration rejection uses
  `task --increment merge-integration-failed`;
- preliminary/done integration uses patch/minor or major release intent;
- guards, PRELIM identity, and finalization can use canonical reads; and
- #105 can include a successful version mutation in its outer rollback
  transaction.

No additional repo-version operation or dependency is required by those
currently declared consumers.
