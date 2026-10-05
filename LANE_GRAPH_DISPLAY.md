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
