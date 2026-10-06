# Constrained Graph Renderer

Status: authoritative project-neutral contract for the terminal graph renderer.

This document defines a deliberately constrained directed-acyclic-graph
renderer.
It is not a general graph-drawing API.  Callers must project their domain data
into this structure before rendering.

The collaboration and review rules in
[COLLABORATIVE_DESIGN_REVIEW.md](COLLABORATIVE_DESIGN_REVIEW.md) apply to this
design.  Verification is subject to [TEST_ADEQUACY.md](TEST_ADEQUACY.md).

## 1. Boundary

The architecture is:

```text
domain data
    |
    v
domain adapter
    |
    v
GraphSiblings DAG + lanes
    |
    v
standalone renderer
    |
    v
complete terminal text
```

The renderer does not know about issues, repositories, providers, status,
selection, caches, GitHub, or RepoWorkflow.

The initial renderer always emits the complete graph from left to right.  It
does not inspect terminal viewport width, wrap, truncate, or provide scrolling.
A caller may use a pager such as `less -RS` for horizontal navigation.

## 2. Node identity

Node text is node identity.

Every node string must therefore be globally unique within one graph.  Duplicate
node text is invalid input.  The renderer does not maintain a separate opaque
node identifier.

A raw node string may contain both data text and annotations.  The renderer does
not interpret either.

## 3. GraphSiblings

The public topology consists of sibling groups:

```text
Graph
  siblings: GraphSiblings[]

GraphSiblings
  nodes: text strings
  to_nodes: GraphSiblings[]
```

A `GraphSiblings` object represents one or more visible nodes that share one
lossless external relationship structure.

Hard invariants:

- `nodes` is non-empty;
- every node string appears in exactly one `GraphSiblings`;
- every `to_nodes` target belongs to the same graph;
- one target may appear at most once in a particular `to_nodes`;
- several source groups may point to the same target group;
- duplicate relationships are errors and are never canonicalized;
- the resulting group graph is a DAG.

A relationship from source group S to target group T represents the complete
cross-product relationship: every node in S connects to every node in T.  A
domain adapter may group nodes only when that cross-product is the exact
semantic relationship and grouping is therefore lossless.  It must not use
grouping merely to make a graph prettier.

## 4. Direction

Edges point from left to right.

For RepoWorkflow lane display this corresponds to prerequisite/leaf toward
dependant/root, but that meaning is outside the generic renderer.

Cycles are invalid public input.  The renderer does not contain a cycle layout
mode.

## 5. Lanes

The graph receives a collection of lanes:

```text
Lane
  nodes: ordered node strings
  colour: colour_function
```

Hard invariants:

- every visible node belongs to exactly one lane;
- lane node sets are pairwise disjoint;
- every lane node exists in the graph;
- every lane is an ordered directed path through the graph;
- a lane may not omit an intermediate node on that path;
- every lane supplies one colour function.

Hidden layout nodes are not visible nodes and do not belong to lanes.

## 6. Colour functions

A colour function is opaque to the renderer:

```text
colour(text) -> formatted_text
```

The renderer does not assume ANSI, terminal escape syntax, or a particular
styling implementation.

The caller supplies:

- one colour function for each lane;
- one default edge-colour function.

Terminal capability discovery and construction of those functions occur outside
this module and must use a capability-aware terminal styling library when
styling is enabled.

## 7. Node colour

Every visible node belongs to a lane.

For each node, the renderer passes the node's raw string and its lane colour
function to the caller-supplied column formatter.  There is no default-colour
visible-node case in valid final input.

The formatter decides which portion of the raw string is data text and invokes
the supplied lane colour function only for that data text.

## 8. Edge colour

Every semantic edge begins conceptually with the supplied default edge colour.

If both semantic endpoint nodes belong to the same lane, the edge uses that
lane's colour instead.

Therefore:

```text
same lane at semantic endpoints -> lane colour
otherwise                       -> default edge colour
```

This rule is based on the semantic endpoints, not on artificial continuation
nodes inserted by layout.

An edge can never legitimately acquire two lane colours because visible lane
membership is pairwise disjoint.

## 9. Column formatter

The renderer calls a formatter once for the visible strings in a graph column.

Input entries are:

```text
(raw_text, lane_colour_function)
```

The formatter owns:

1. determining the target display width for that column;
2. optionally decomposing raw text into data text and annotation text;
3. applying alignment and padding;
4. applying the supplied colour function to data text;
5. formatting annotation text independently;
6. returning formatted strings and their common display width.

The returned width is terminal-cell display width.  Styling/control sequences
do not contribute to it.

The renderer does not understand annotations and does not calculate visible
width from encoded-string length.

Different graph columns may have different widths.

## 10. Column assignment

The renderer assigns deterministic left-to-right columns from the validated DAG.

Input ordering must not affect the result.  Canonical tie-breaking is required.

A semantic edge may span more than one assigned column.

## 11. Hidden continuation nodes

A long semantic edge is normalized through one hidden continuation node for
each skipped column.

Every hidden continuation records:

- the original semantic source node;
- the original semantic target node;
- the original semantic edge identity;
- its assigned column.

After normalization every layout edge crosses exactly one adjacent-column
boundary.

Hidden continuations:

- are layout-only;
- are not visible node strings;
- are not lane members;
- never become semantic dependency endpoints;
- use the colour derived from their original semantic endpoints.

## 12. Siblings and cousins

Sibling nodes within one `GraphSiblings` remain compact.

Distinct sibling groups are independent layout entities.  When their outgoing
tracks cannot be shared losslessly they are cousins and retain independent
routing space.

The renderer must never collapse distinct groups during layout merely because
doing so would reduce width or crossings.

## 13. Adjacent-column routing

All relationships between one pair of adjacent columns are considered together.

Routing is a layout operation over already-established graph semantics.  It may
choose ordering, tracks, bends, and crossings but may not create or remove a
relationship.

Unrelated paths may cross without becoming a junction.  Horizontal geometry is
visually dominant at an unrelated horizontal/vertical crossing.

A successful route must retain the identity of each original semantic edge.

## 14. Route quality

Semantic correctness is a hard gate.  Among semantically valid layouts, the
renderer uses deterministic route-quality preferences rather than preserving a
mechanical track choice.

Quality is compared lexicographically using independently measurable geometry:

1. maximum vertical span;
2. total vertical routing cells;
3. bend count;
4. adjacent opposite-direction vertical tracks;
5. unrelated crossing count;
6. vertical-track count;
7. total rendered width;
8. canonical deterministic tie-breaking.

Long edges consider only a bounded set of candidate rows derived from visible
rows plus a bounded fallback below them.  A candidate row through an
intermediate column is invalid when that row contains a visible node.

A long-edge route should remain between its endpoint rows when a valid route is
available there.  It must not dip below both endpoints merely because a private
long-edge track was allocated mechanically.

Long edges may reuse a routing row only when all semantic edges sharing that
row have one common source or one common target.  Other collinear sharing is
not considered lossless.

Adjacent opposite-direction vertical tracks such as `↓↑` are valid geometry,
not a semantic error.  Track ordering should avoid them when an equally valid
deterministic arrangement can separate the directions.

Group ordering may use bounded local improvement against already-placed
predecessor rows.  It must preserve each `GraphSiblings` object as an
indivisible unit and may never trade semantic correctness for a lower quality
score.

## 15. Semantic validation

The router is not its own oracle.

Before text emission, an independent layout validator must establish that the
logical geometry reconstructs exactly the semantic relationships supplied by
the public graph.

For each visible node:

```text
rendered reachable targets == semantic targets
```

It must also verify that continuation nodes reconstruct their original long
edge and never appear as semantic endpoints.

A candidate that cannot satisfy the semantic validator is not renderable.

## 16. Unsupported layout

The renderer must never emit an ambiguous graph merely to produce output.

If a valid supported layout cannot be constructed, it returns an explicit
unsupported-layout error.  Domain callers may then render components,
subgraphs, or a plain relationship list.

## 17. Determinism

For the same semantic graph, lanes, formatter results, and rendering options,
the renderer must produce the same logical layout and terminal text regardless
of:

- sibling-list input order;
- target-list input order;
- lane-list input order;
- provider ordering;
- process restart.

Platform-specific terminal styling may differ only where the supplied colour
functions differ.

## 18. RepoWorkflow adapter

RepoWorkflow maps current relationship and lane-selection state into this
generic contract.

The adapter owns:

- construction of raw node strings;
- lossless `GraphSiblings` grouping;
- ordered complete lane paths;
- lane colour functions;
- the default edge-colour function;
- the node-column formatter.

It does not supply columns, continuation nodes, routes, crossings, or glyphs.

## 19. Verification

Specification tests must cover at least:

- zero/one/many groups and nodes;
- one/two/many siblings;
- chains, convergence, divergence, and long edges;
- directional cousin overlap;
- disconnected components;
- same-lane and default-colour edges;
- long same-lane edge colour propagation;
- every public input-invariant failure;
- input-order determinism;
- semantic reconstruction after routing;
- terminal-cell width independent of styling codes;
- exact RepoWorkflow adapter projection.

Property tests should generate bounded valid constrained DAGs.  A generated case
must either render with exact semantic equivalence or fail explicitly as
unsupported.
