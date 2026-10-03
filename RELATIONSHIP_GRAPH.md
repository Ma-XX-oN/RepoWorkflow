# Direct Relationship Graph Schema

Status: authoritative schema/invariant contract for RWF issue relationships.

This document defines the versioned in-memory/durable relationship value that
workflow-state storage will persist in later issues.  It complements
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md), which defines the
repository-neutral decomposition semantics.

## 1. Schema version

The initial schema version is `1`.

A graph value has this shape:

```json
{
  "schema_version": 1,
  "issues": {
    "10": {
      "umbrella": "1",
      "shared_umbrellas": ["50"],
      "depends_on": ["7"],
      "umbrella_depends_on": ["40"],
      "branch_base": "issue-7",
      "integration_target": "main"
    }
  }
}
```

Issue identifiers are positive decimal integers serialized as canonical decimal
strings without leading zeroes.

## 2. Relationship fields

Every issue record contains all six relationship fields.

### 2.1 `umbrella`

The one owning umbrella, or `null`.

Ownership says that the child contributes to the umbrella outcome.

It does not create executable ordering.

### 2.2 `shared_umbrellas`

Zero or more reusable capability umbrellas consumed by this issue/umbrella.

Shared attachment records architectural reuse.

It does not create executable ordering.

### 2.3 `depends_on`

The exact direct leaf dependencies that must be complete before this issue is
ready.

This is the authoritative executable scheduling edge set.

Only direct blockers are stored.  Transitive prerequisites are obtained by
graph traversal.

### 2.4 `umbrella_depends_on`

Direct completion-level umbrella dependencies.

These form a high-level roadmap and must not be used as a substitute for exact
leaf dependencies.

A leaf may still be executable while its owning umbrella has an unresolved
umbrella dependency.

### 2.5 `branch_base`

The explicit Git branch/base relationship, or `null`.

Branch base is a Git-history fact.

It never creates an issue dependency implicitly.

### 2.6 `integration_target`

The explicit integration target, or `null`.

Integration target is independent of ownership, direct dependency, and branch
base.

## 3. Distinct relationship types

The schema intentionally stores these concepts independently:

1. child ownership;
2. shared umbrella attachment;
3. direct leaf dependency;
4. direct umbrella dependency;
5. branch base;
6. integration target.

No field may be reconstructed by guessing from another field.

In particular:

- branch ancestry does not imply dependency;
- umbrella membership does not imply dependency;
- shared attachment does not imply dependency;
- leaf dependency does not dictate branch base.

## 4. Readiness

For a leaf issue `I`:

```text
ready(I)
  iff every issue in I.depends_on is complete
```

The following do not independently block leaf readiness:

- `umbrella`;
- `shared_umbrellas`;
- `umbrella_depends_on`;
- `branch_base`;
- `integration_target`.

A completed issue is not returned as a ready work candidate.

## 5. Direct dependency invariants

The direct leaf graph must:

- contain no self edge;
- reference known graph issues for every executable direct dependency;
- contain no cycles;
- contain only direct blockers.

If `A -> B -> C`, storing `A -> C` merely because it is transitively true is
incorrect unless A independently consumes C's interface.

The pure schema validator can detect cycles and unknown edges.

Whether an edge is unnecessarily transitive requires semantic/decomposition
review or a higher-level graph diagnostic.

## 6. Umbrella invariants

An issue has at most one owning umbrella.

A shared umbrella attachment does not make the attached issue a child of that
umbrella.

An issue cannot own itself, attach to itself, directly depend on itself, or
declare itself as an umbrella dependency.

Reusable children stay owned by their shared-capability umbrella rather than
being copied or multi-parented into consumers.

## 7. Reconstruction

The versioned value must round-trip without conflating relationship types.

Given a valid serialized graph, reconstruction must preserve:

- exact ownership;
- shared attachments;
- direct leaf dependencies;
- umbrella dependencies;
- branch base;
- integration target.

Canonical output sorts issue identifiers and issue-reference arrays
numerically for deterministic storage/diffing.

## 8. Persistence boundary

This issue defines the relationship value and pure reconstruction/readiness
semantics.

It does not define where the value is stored or how concurrent durable writes
are performed.

Those responsibilities belong to:

- #78 for durable versus clone-local ownership/layout;
- #99/#100/#101 for concurrency, recovery, and generic storage;
- #145 for the canonical relationship graph store/reader.

No caller should parse GitHub issue prose as the durable relationship database
once #145 exists.

## 9. Failure semantics

Malformed relationship data fails closed.

Reject at least:

- unsupported schema versions;
- missing/unknown fields;
- invalid issue identifiers;
- duplicate relationship entries;
- self relationships;
- unknown direct dependency targets;
- direct dependency cycles.

Failure must not silently reinterpret an invalid relationship as no
relationship.

## 10. Testing

Contract coverage must prove:

- lossless reconstruction of all relationship types;
- ownership/attachment do not create scheduling edges;
- branch base does not create a scheduling edge;
- unresolved direct dependencies block exactly their consumer;
- completing a direct dependency makes the consumer ready;
- direct dependency cycles are rejected;
- unknown direct dependency targets are rejected;
- self relationships are rejected;
- unsupported schema versions are rejected.

The pure relationship model is implemented in
`repo_workflow/relationships.py`; durable persistence remains separate.
