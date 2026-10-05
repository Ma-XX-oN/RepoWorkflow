# Native Ticket Dependency Adapter Contract

Status: authoritative provider-neutral read/write contract for native ticket
dependency relationships.

## Boundary

Core RWF invokes the repository-owned command configured as
`dependencyCommand`.  This is a companion to, not an extension of, the
read-only `repo-info` boundary.

Core RWF contains no GitHub, `gh`, Blocked-by, or provider API syntax.

## Operations

Read the complete direct dependency set for one issue:

```text
dependency get ISSUE
```

Replace the complete direct dependency set for one issue:

```text
dependency replace ISSUE [DEPENDENCY...]
```

Replacement is exact-set replacement, not merge/add.  An empty tail requests an
empty dependency set.

## Successful result

Both operations return exactly:

```json
{
  "schema_version": 1,
  "issue": 64,
  "dependencies": [2, 9, 54]
}
```

Rules:

- `issue` and every dependency are positive integers;
- `issue` must equal the requested issue;
- dependencies are sorted ascending, unique, and may be empty;
- self-dependency is invalid;
- dependency ordering has no semantic meaning;
- after replace, the returned set must exactly equal the requested normalized
  set and therefore confirms the complete provider state requested.

## Failure and capability semantics

A provider that cannot read or replace native dependencies exits non-zero with
a diagnostic.  Unsupported capability, authentication/permission failure,
transport failure, malformed provider data, and mutation failure are errors;
none may be represented as an empty successful dependency set.

Core RWF validates successful JSON strictly.  Unknown fields, malformed JSON,
unsupported schema versions, wrong issue identity, duplicate/unsorted IDs, or a
replace result that differs from the requested complete set fail explicitly.

## Repository-state invariant

The adapter may mutate the external ticket provider only.  Both operations must
leave local Git repository state, refs, HEAD, index, and worktree unchanged.
Core RWF checks this boundary.

## Atomicity/reconciliation boundary

The contract does not claim that an external provider offers transactional
multi-edge replacement.  A non-zero replace result is never reported as
success.  Callers that need recovery after an unknown/partial provider mutation
must reread with `dependency get` and reconcile explicitly; they must not
assume either the old or requested set.

## Provider implementation

#210 owns the GitHub implementation and maps this contract to GitHub native
issue dependencies.  Provider-specific invocation and API details remain
outside core RWF.
