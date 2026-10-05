# Lane Graph Display

Status: authoritative public display companion to #205/#219.

## Human output

Lane selection is immediately inspectable:

```text
rwf lanes select <roots...>
rwf lanes select add <roots...>
rwf lanes select remove <roots...>
rwf lanes list
```

Successful selection mutations and `lanes list` render the selected dependency
graph.  Graph direction is leaf to root.

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

Normal graph cells do not include issue titles.  Titles are available through
`rwf issue list` / `rwf issue info`; `--links` is an explicit optional
graph expansion.

Changing annotations must not change dependency topology.  Colour is
supplementary and follows the persistent global `auto|always|never` setting.

## Topology

Canonical direct dependencies determine graph connectors.  Rendering never
creates, removes, or infers dependency edges.

Leaf-to-root chains and branch/convergence structures use Unicode box-drawing
characters.  Optional links are display metadata; issue titles are deliberately
excluded from graph cells so metadata cannot inflate topology coordinates.
Lane assignment is a node label and does not determine graph topology.
