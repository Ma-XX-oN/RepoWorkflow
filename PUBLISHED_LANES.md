# Published Lane Display Contract

Status: authoritative companion to
[WORK_GRAPH_METHODOLOGY.md](WORK_GRAPH_METHODOLOGY.md) for published lane
presentation and coordination notation.

When a work graph is divided into named parallel lanes, lane names use uppercase
letters and tree/list displays qualify each issue with its lane letter:

```text
A56
```

means **Lane A, issue #56**.  A descriptive ticket type may be prefixed,
for example `E:A56` for an Epic.

For example:

```text
A227 → A228 ─┐
               ├→ #230
B229 ─────────┘
```

The notation is presentation/coordination syntax only:

- `A` is the published lane identifier;
- `56` is GitHub issue #56;
- `A56` does not create a new issue identifier or dependency relationship;
- dependency storage and issue references continue to use issue number `#56`;
- the same issue must not be presented as belonging to two concurrent published
  lanes unless the lane model explicitly supports shared membership;
- nodes outside the published lanes may remain `#N`, particularly convergence
  nodes and existing external prerequisites;
- published lane summaries include the percentage of lane issues already
  complete.

Lane letters are stable within a published lane plan.  Reordering presentation
must not silently rename Lane A to Lane B or otherwise change lane identity.
