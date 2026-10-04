# Synchronized Issue Metadata

Status: authoritative contract for provider-derived issue metadata snapshots used
by offline RWF workflow operations.

## 1. Purpose and authority

RWF stores normalized issue metadata for every issue represented in the
canonical synchronized relationship graph.  The initial snapshot contains only
the issue number and title needed by later branch-name derivation.

This snapshot is provider-derived durable/shared state.  It is **not** authority
for dependencies, lifecycle, readiness, or provider ticket state.

Dependency authority remains the canonical relationship graph.  Lifecycle
authority remains the lifecycle store.

## 2. Placement

The snapshot follows the durable repository-state ownership defined by
[STATE_LAYOUT.md](STATE_LAYOUT.md) and is stored through the generic durable
state store at:

```text
.repoworkflow/state/issues/metadata.json
```

The semantic state-store key is `issues/metadata`.

The value schema is:

```json
{
  "schema_version": 1,
  "issues": {
    "229": {
      "number": 229,
      "title": "Persist synchronized issue titles for offline workflow use"
    }
  }
}
```

Issue keys are canonical positive decimal strings.  Each embedded number must
match its key.  Titles are non-empty provider-neutral text.

## 3. Refresh boundary

A metadata refresh:

1. reads the canonical relationship graph to obtain the complete issue scope;
2. requests normalized issue information through the `repo-info` boundary for
   every issue in that scope;
3. validates every provider result before mutating durable metadata;
4. atomically creates or replaces one complete snapshot.

Provider failure, missing issues, malformed results, or empty titles fail the
refresh.  A failed refresh does not publish a partial snapshot or report
complete synchronization.

#214 consumes this refresh after successful mutating dependency
synchronization.  #229 is an input to #214; metadata refresh does not depend on
the dependency-sync CLI.

## 4. Offline reader

`IssueMetadataStore.issue(N)` reads only the durable local snapshot.  It does
not accept provider configuration and cannot fall back to `repo-info`.

Missing snapshot data or a missing requested issue fails explicitly.  Normal
workflow consumers therefore remain genuinely network-independent after
metadata has been synchronized.

## 5. Invariants

- metadata is normalized and provider-neutral;
- metadata never replaces relationship or lifecycle authority;
- provider failure never becomes an empty title;
- refresh publishes the complete graph scope or no new snapshot;
- offline reads are read-only and never contact a ticket provider;
- issue-number identity is preserved exactly across provider, snapshot, and
  local reader.

## 6. Verification

Tests cover complete multi-issue refresh, title changes, restart/readback,
provider failure with prior-state preservation, malformed/empty metadata,
missing local metadata, missing issue metadata, and offline reads with the
provider adapter deliberately configured to fail if touched.
