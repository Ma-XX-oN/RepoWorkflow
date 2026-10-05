# Synchronized Issue Metadata

Status: authoritative contract for provider-derived issue metadata snapshots used
by offline RWF workflow operations.

## 1. Purpose and authority

RWF stores normalized issue metadata for every issue represented in the
canonical synchronized relationship graph.  The current snapshot contains normalized issue number, title, open/closed state,
and canonical provider-neutral link.  Title-only schema-v1 snapshots remain
readable for legacy title consumers but are explicitly incomplete for lane
inspection until refreshed.

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
  "schema_version": 2,
  "issues": {
    "229": {
      "number": 229,
      "title": "Persist synchronized issue titles for offline workflow use",
      "state": "closed",
      "link": "https://example.invalid/issues/229"
    }
  }
}
```

Issue keys are canonical positive decimal strings.  Each embedded number must
match its key.  Titles are non-empty provider-neutral text.

## 3. Refresh boundary

A complete metadata refresh reads the canonical relationship graph for scope,
requests normalized issue information through `repo-info`, validates every
result, then atomically replaces the complete snapshot.

A scoped refresh may update a declared subset already represented in the
canonical graph.  It validates the whole requested subset before publishing
and preserves all other complete snapshot entries unchanged.  A scoped refresh
cannot introduce metadata for an issue absent from the canonical graph.

Provider failure, missing issues, malformed results, or empty titles fail the
refresh.  A failed refresh does not publish a partial snapshot or report
complete synchronization.

#214 consumes this refresh after successful mutating dependency
synchronization.  #229 is an input to #214; metadata refresh does not depend on
the dependency-sync CLI.

## 4. Offline reader

`IssueMetadataStore.issue(N)` reads only the durable local snapshot.  It does
not accept provider configuration and cannot fall back to `repo-info`.

Missing snapshot data or a missing requested issue fails explicitly.
`display_issue(N)` additionally requires state and link; a schema-v1
title-only record fails with an explicit refresh diagnostic rather than
inventing display data.  Normal workflow consumers therefore remain genuinely
network-independent after metadata has been synchronized.

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


## Incomplete v2 migration records

Scoped refresh of a legacy schema-v1 snapshot must not force unrelated provider
reads.  When a v1 snapshot is first rewritten as schema v2, untouched legacy
entries are represented explicitly as:

```json
{
  "number": 20,
  "title": "Twenty",
  "state": null,
  "link": null
}
```

The pair `state=null, link=null` is the only valid incomplete v2 shape.
It preserves provider-derived title information without fabricating display
state or links.  `issue(N)` may read such an entry; `display_issue(N)` must
fail explicitly until that issue is refreshed.

Mixed shapes such as a non-null state with null link, or null state with a
non-null link, are invalid.  A later scoped refresh upgrades only the requested
entries and leaves already complete or still-incomplete unrelated entries
untouched.
