# Direct Dependency Graph

Status: authoritative graph contract for RepoWorkflow scheduling.

The durable synchronized ticket representation is defined in
[TICKET_STATE.md](TICKET_STATE.md).

## Graph model

Each known ticket contributes one node:

```text
ticket number
exact synchronized title
direct dependencies
```

Only direct dependency edges participate in the executable graph.

For issue `I`:

```text
ready(I)
  iff every issue in I.depends_on is complete
```

Completed issues are not returned as ready work.

## Invariants

The graph must:

- use positive canonical ticket numbers;
- contain every referenced direct dependency;
- contain no self edges;
- contain no duplicate direct dependencies;
- contain no cycles;
- store direct blockers rather than redundant transitive prerequisites.

If `A -> B -> C`, do not also store `A -> C` unless A independently
requires C's interface.

## What is not part of this graph

RepoWorkflow does not store a second relationship graph for container
ownership, membership, or attachment.

Branch parent/integration target is also not part of the ticket graph.

Human-facing Initiative/Epic/Feature classification is expressed only in ticket
titles and has no graph semantics.

Branch-parent identity belongs to Git branch history and is governed by
[PARENT_BRANCH_WORKFLOW.md](PARENT_BRANCH_WORKFLOW.md).

## Determinism

Issue IDs and dependency lists are serialized numerically in ascending order.
Reconstruction preserves exact titles and exact direct dependency sets.

Malformed graph data fails closed.

## Verification

Tests separately prove:

- schema/serialization correctness;
- exact direct-dependency reconstruction;
- unknown/self/duplicate/cyclic dependency rejection;
- readiness semantics;
- deterministic ordering;
- migration into the current synchronized ticket representation;
- absence of runtime consumers for removed relationship fields.

TEST_ADEQUACY.md applies.
