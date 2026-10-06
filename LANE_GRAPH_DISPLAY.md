# Lane Graph Display

Status: authoritative public display companion to #205/#219.

The generic renderer contract is defined in
[GRAPH_RENDERER.md](GRAPH_RENDERER.md).  This document defines the
RepoWorkflow-specific projection and public presentation.

## Human output

Lane selection is immediately inspectable:

```text
rwf lanes select <roots...>
rwf lanes select add <roots...>
rwf lanes select remove <roots...>
rwf lanes view
```

Successful selection mutations and `lanes view` render the selected dependency
graph.  Graph direction is leaf to root.

`rwf lanes list [lane] [--links]` is deliberately not a graph.  It is the
lane-membership inventory, analogous to `rwf issue list`: issues are grouped
by lane and displayed as `#N  title`, with the synchronized canonical link
appended only when `--links` is requested.

The machine-readable selection record remains available explicitly:

```text
rwf lanes select <roots...> --json
rwf lanes select add <roots...> --json
rwf lanes select remove <roots...> --json
```

## Node notation and formatting

RepoWorkflow projects each visible issue to one raw node string using
`lane.issue`.  Explicit roots are marked `*`; closed issues are marked `✓`;
combined annotation order is `*✓`.

The raw string, including annotations, is passed to the generic renderer.  The
RepoWorkflow column formatter may decompose that string into annotation and data
text.  It aligns nodes in one column to one terminal-cell width and applies the
lane colour function only to the data text.

For example:

```text
*✓A.63
 *B.65
```

Normal graph nodes do not include issue titles or links.  Those are available
through `rwf lanes list` and issue list/info commands.

The generic renderer does not inspect terminal viewport width and does not
truncate or wrap the graph.  The complete graph is emitted left to right.  A
pager such as `less -RS` may be used for horizontal navigation.

## Lane path invariant

Every selected issue belongs to exactly one lane.

Each lane is a complete directed path through the selected dependency graph.
When one path branches, at most one branch may continue the existing lane; the
other branch starts another lane.  At convergence, the converged node belongs
to exactly one predecessor lane.

The decomposition is deterministic.  Lane membership never duplicates a node.

## Topology projection

RepoWorkflow projects the selected dependency graph into the constrained
`GraphSiblings` model.

A sibling group may contain several nodes only when grouping them preserves
their complete external relationship structure.  The adapter must not group
nodes merely for visual convenience.

Canonical direct dependencies remain authoritative.  Rendering never performs
semantic transitive reduction and never invents a dependency.

Long direct dependencies may span several visual columns.  The generic
renderer inserts hidden continuation nodes for skipped columns.  Those nodes are
layout-only and retain the original semantic source and target.

## Lane and edge colour

Colour functions are produced outside the generic graph renderer by the
terminal styling boundary.  The renderer treats them as opaque functions and
does not assume ANSI or another terminal escape format.

Every visible node uses its lane colour.

For an edge:

- if its two semantic endpoint nodes belong to the same lane, use that lane
  colour;
- otherwise use the supplied default edge colour.

The rule continues to use the original semantic endpoints when a long edge is
split through hidden continuation nodes.

For example, if lanes are:

```text
[A, X]
[B, Z]
[C, Y]
[D]
```

and dependencies include:

```text
A -> X
B -> X
B -> Y
C -> Y
B -> Z
D -> Z
```

then `A -> X`, `B -> Z`, and `C -> Y` use lane colours.  The other three
edges use the default edge colour.

## Routing semantics

All connections between one pair of adjacent columns are treated as one routing
problem.  The renderer may choose deterministic ordering, tracks, bends, and
crossings but may not change semantic connectivity.

Sibling expansion is a canonical representation, not a competing routing
algorithm.  Cousin groups retain independent routing space when their outgoing
tracks differ.

Unrelated paths may cross without becoming a junction.  The logical layout is
validated independently before terminal text is emitted.

Every canonical direct dependency is retained as one semantic route identity.
`rwf lanes view --debug` reports those route identities, including long-edge
continuation information.

## Unsupported layout

If the constrained renderer cannot produce a semantically valid supported
layout, it must fail explicitly rather than emit an ambiguous graph.

RepoWorkflow may then fall back to a safe component/subgraph or relationship
listing.  Ambiguous pretty output is never an acceptable fallback.
