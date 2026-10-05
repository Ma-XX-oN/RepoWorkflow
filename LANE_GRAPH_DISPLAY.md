# Lane Graph Display

Status: authoritative public display companion to #205/#219.

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

## Node notation

Nodes use `lane.issue`.  Explicit roots are marked `*`; closed issues are
marked `✓`; combined annotation order is `*✓`.

Within each visual graph column:

- reserve only the annotation width actually required by that column;
- right-align annotations directly against `lane.issue`;
- align identifiers on the `.` regardless of annotation/lane/issue width.

For example:

```text
*✓A.63
 *B.65
```

Normal graph cells do not include issue titles.  Titles and optional links are
available through `rwf lanes list` and the issue list/info commands.

Changing annotations must not change dependency topology.  Colour is
supplementary and follows the persistent global `auto|always|never` setting.

## Topology

Canonical direct dependencies determine graph connectors.  Rendering never
creates, removes, or infers dependency edges.

Leaf-to-root chains and branch/convergence structures use Unicode box-drawing
characters.  Issue titles and links are deliberately excluded from graph cells
so metadata cannot inflate topology coordinates.
Lane assignment is a node label and does not determine graph topology.


## Edge identity and bypass tracks

Every canonical direct dependency is rendered as one identifiable logical
route.  The renderer chooses deterministic adjacent primary edges for the
readable backbone.  Any remaining direct dependency uses its own bypass track,
including direct edges that skip over an existing transitive path.

For example, when all three direct facts exist:

```text
145 -> 185
185 -> 216
145 -> 216
```

the direct 145 -> 216 edge is shown separately from the primary
145 -> 185 -> 216 path rather than merged into it.

Routes may visibly share geometry only when they genuinely share the same
source before branching or the same target after convergence.  An unrelated
horizontal/vertical crossing is rendered as `╳`, meaning crossing without a
dependency junction.

The renderer never performs semantic transitive reduction.  `lanes view
--debug` reports every direct edge and its assigned primary/bypass route.
