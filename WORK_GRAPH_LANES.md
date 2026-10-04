# Published Work Lanes

Status: authoritative companion to
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) for published lane
presentation and coordination.

## Lane display notation

When a work graph is divided into named parallel lanes, lane names use uppercase
letters and tree/list displays qualify each issue with its lane letter:

```text
A.56
```

means **Lane A, issue #56**.

For example:

```text
A.227 → A.228 ─┐
               ├→ #230
B.229 ─────────┘
```

The notation is presentation/coordination syntax only:

- `A` is the published lane identifier;
- `56` is GitHub issue #56;
- `A.56` does not create a new issue identifier or dependency relationship;
- dependency storage and issue references continue to use issue number `#56`;
- the same issue must not be presented as belonging to two concurrent published
  lanes unless the lane model explicitly supports shared membership;
- nodes outside the published lanes may remain `#N`, particularly convergence
  nodes and existing external prerequisites;
- published lane summaries include the percentage of lane issues already
  complete.

Lane letters are stable within a published lane plan.  Reordering presentation
must not silently rename Lane A to Lane B or otherwise change lane identity.

## Relationship to scheduling

Published lanes are coordination views over the authoritative issue graph.
They do not alter dependency truth, readiness, ownership, parent topology, or
integration topology.

Workers must re-check the direct issue blockers before beginning the next issue
in a lane.  A lane letter never supplies a prerequisite that is absent from the
issue dependency graph.
