# Lane Graph Display

Status: authoritative public display companion to #205/#219.

Generic graph structure, validation, routing, formatting, colour propagation,
and fallback behaviour are defined in
[GRAPH_RENDERER.md](GRAPH_RENDERER.md).

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
appended only when `--links` is requested.  Each non-empty lane group uses
that lane's terminal colour when colour output is enabled.

The machine-readable selection record remains available explicitly:

```text
rwf lanes select <roots...> --json
rwf lanes select add <roots...> --json
rwf lanes select remove <roots...> --json
```

## Node notation

RepoWorkflow maps each issue to one raw graph-node string.

Node IDs use `[type:]laneissue` with no separator between lane and issue.
The optional synchronized-title annotations are `I:` for `Initiative:`,
`E:` for `Epic:`, and `F:` for `Feature:`.  Explicit roots are marked
`*`; closed issues are marked `✓`; combined status order is `*✓`.

The RepoWorkflow column formatter:

- reserves only the status width required by that visual graph column;
- reserves a two-cell type slot only when that same column contains a typed
  node;
- right-aligns status annotations directly against the node ID;
- aligns lane letters within each visual graph column;
- passes the optional type annotation plus lane/issue ID through the lane
  colour function;
- leaves status annotation styling independent.

For example, a mixed typed/untyped column may contain:

```text
*✓E:A63
    B65
```

A column containing only ordinary tickets reserves no type slot.

Normal graph nodes do not include issue titles or links.  Those remain available
through `rwf lanes list` and the issue list/info commands.

Changing annotations must not change dependency topology.

## RepoWorkflow projection

The lane display adapter projects synchronized RepoWorkflow state into the
constrained generic renderer.

It supplies:

- globally unique raw node strings;
- lossless `GraphSiblings` groups;
- complete ordered lane paths;
- one colour function for every lane;
- one default edge-colour function;
- the RepoWorkflow column formatter.

It does not supply graph columns, hidden continuation nodes, route tracks,
crossings, or Unicode glyphs.

Before sibling grouping, the adapter performs deterministic transitive
reduction of the visible dependency DAG for display only.  A canonical direct
dependency may be omitted from the display when another displayed directed
path connects the same source and target.  This preserves prerequisite
reachability exactly while removing redundant shortcut connectors.

The canonical relationship store is never modified by display reduction.

Sibling grouping is permitted only when the grouped issues have identical
incoming and outgoing relationships in the reduced display graph.  Grouping
therefore cannot change display reachability.

## Lane completeness

Every visible issue belongs to exactly one selected lane.

Within the projected graph, the issues assigned to one lane must form a complete
directed path.  The adapter reconstructs dependency order and rejects a lane
whose consecutive nodes are not directly related.  It never inserts a missing
semantic issue merely to make a lane renderable.

## Edge colour

Node data text uses its lane colour.

For each retained display dependency:

- if both semantic endpoint issues belong to the same lane, the dependency uses
  that lane colour;
- otherwise it uses the default edge colour.

A direct edge that spans several visual columns keeps the same colour across
all hidden continuation segments because those segments retain the original
semantic endpoints.

The graph engine treats colour functions as opaque.  It does not assume ANSI
or another terminal control syntax.

## Topology

Canonical direct dependencies determine prerequisite reachability.  The
RepoWorkflow adapter transitively reduces the visible DAG before passing it to
the generic renderer.  The reduction removes only display shortcuts whose
reachability is already represented by another path.

The generic renderer itself does not infer or remove relationships: it renders
the reduced graph supplied by the adapter exactly.

Long retained display dependencies are represented with hidden continuation
nodes in each skipped graph column.  Hidden nodes are layout-only and never
appear as issue nodes or lane members.

After normalization every layout edge crosses one adjacent column boundary.

Sibling groups remain compact.  Distinct groups retain separate routing space
when their tracks cannot be shared losslessly.

Unrelated horizontal and vertical routes may cross without becoming a semantic
junction.  Horizontal geometry is visually dominant at such a crossing.

## Diagnostics

`rwf lanes view --debug` reports one route identity for every retained display
dependency.  Canonical relationship data remains available from the
relationship store and provider-facing diagnostics.

Adjacent relationships report an adjacent or bundled route.  A relationship
that spans visual columns reports a long route together with its hidden
continuation columns.

Diagnostics describe the renderer's logical route identity.  They do not make
route placement or track numbers part of the public semantic contract.

## Width and paging

The initial graph renderer always emits the complete graph from left to right.

It does not inspect terminal viewport width, wrap the graph, truncate columns,
or provide an interactive horizontal viewport.

A terminal user may use a pager such as:

```text
rwf lanes view | less -RS
```

Horizontal scrolling is therefore a presentation concern outside the graph
engine.
