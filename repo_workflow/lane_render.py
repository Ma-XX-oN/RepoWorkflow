from __future__ import annotations

from pathlib import Path
import sys

from .issue_metadata import IssueMetadataStore
from .lane_routes import plan_routes, render_route_cell
from .lane_selection import LaneSelection, LaneSelectionStore
from .relationship_store import RelationshipStore
from .state_store import StateStoreError, WriterIdentity, clone_local_store


SETTINGS_KEY = "settings/display"
VALID_COLORS = {"auto", "always", "never"}
_COLORS = (31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96)


class LaneRenderError(RuntimeError):
  pass


def color_setting(root: Path) -> str:
  try:
    value = clone_local_store(root).read(SETTINGS_KEY)["value"]
  except StateStoreError as error:
    if "record is missing:" in str(error):
      return "auto"
    raise LaneRenderError(str(error)) from error
  color = value.get("color") if isinstance(value, dict) else None
  if color not in VALID_COLORS:
    raise LaneRenderError("invalid persistent color setting")
  return color


def set_color_setting(root: Path, color: str, writer: WriterIdentity) -> str:
  if color not in VALID_COLORS:
    raise LaneRenderError("color must be auto, always, or never")
  store = clone_local_store(root)
  value = {"color": color}
  try:
    current = store.read(SETTINGS_KEY)
  except StateStoreError as error:
    if "record is missing:" not in str(error):
      raise LaneRenderError(str(error)) from error
    store.create(SETTINGS_KEY, value, writer)
  else:
    store.replace(SETTINGS_KEY, current["revision"], value, writer)
  return color


def render_lanes(
  root: Path,
  *,
  lane: str | None = None,
  links: bool = False,
  titles: bool = False,
  diagnostics=None,
) -> tuple[str, ...]:
  selection = LaneSelectionStore(root).read().value
  if selection is None:
    raise LaneRenderError("lane selection is missing")
  graph = RelationshipStore(root).read().graph

  visible = set(selection.closure)
  if lane is not None:
    lane = lane.upper()
    if lane not in set(selection.assignment.values()):
      raise LaneRenderError(f"unknown selected lane: {lane}")
    visible = {
      issue
      for issue in selection.closure
      if selection.assignment[issue] == lane
    }

  metadata = _metadata(root, tuple(sorted(visible, key=int)))
  return _render_graph(
    selection,
    graph,
    visible,
    metadata,
    links=links,
    titles=titles,
    color=_color_enabled(root),
    diagnostics=diagnostics,
  )


def _render_graph(
  selection: LaneSelection,
  graph,
  visible: set[str],
  metadata: dict[str, dict],
  *,
  links: bool,
  titles: bool,
  color: bool,
  diagnostics=None,
) -> tuple[str, ...]:
  if not visible:
    return ()

  dependencies = {
    issue: tuple(
      dependency
      for dependency in graph.issue(issue).depends_on
      if dependency in visible
    )
    for issue in visible
  }
  depths = _depths(dependencies)

  columns = sorted(set(depths.values()))
  annotation_width: dict[int, int] = {}
  lane_width: dict[int, int] = {}
  issue_width: dict[int, int] = {}
  labels: dict[str, str] = {}

  roots = set(selection.roots)
  for column in columns:
    issues = [issue for issue in visible if depths[issue] == column]
    annotation_width[column] = max(
      (
        len(
          ("*" if issue in roots else "")
          + ("✓" if metadata[issue]["closed"] else "")
        )
        for issue in issues
      ),
      default=0,
    )
    lane_width[column] = max(
      (len(selection.assignment[issue]) for issue in issues),
      default=1,
    )
    issue_width[column] = max((len(issue) for issue in issues), default=1)

  for issue in visible:
    column = depths[issue]
    annotation = (
      ("*" if issue in roots else "")
      + ("✓" if metadata[issue]["closed"] else "")
    )
    label = (
      annotation.rjust(annotation_width[column])
      + selection.assignment[issue].rjust(lane_width[column])
      + "."
      + issue.rjust(issue_width[column])
    )
    if titles and metadata[issue]["title"]:
      label += f"  {metadata[issue]['title']}"
    if links:
      label += f"  {metadata[issue]['link']}"
    labels[issue] = label

  column_width = {
    column: max(
      len(labels[issue])
      for issue in visible
      if depths[issue] == column
    )
    for column in columns
  }
  column_start: dict[int, int] = {}
  cursor = 0
  for column in columns:
    column_start[column] = cursor
    cursor += column_width[column] + 5

  route_plan = plan_routes(
    selection,
    dependencies,
    depths,
    column_start,
    column_width,
    labels,
  )
  if diagnostics is not None:
    diagnostics.routed_edges = [
      route.diagnostic()
      for route in route_plan.routes
    ]

  width = max(
    column_start[depths[issue]] + len(labels[issue])
    for issue in visible
  )
  canvas = [
    [" "] * width
    for _ in range(route_plan.max_y + 1)
  ]

  for (x, y), edges in route_plan.cells.items():
    if 0 <= y < len(canvas) and 0 <= x < width:
      canvas[y][x] = render_route_cell(edges)

  token_spans: list[tuple[int, int, int, str]] = []
  for issue in sorted(visible, key=int):
    column, y = route_plan.positions[issue]
    x = column_start[column]
    label = labels[issue]
    for offset, char in enumerate(label):
      canvas[y][x + offset] = char
    token_spans.append(
      (y, x, x + len(label), selection.assignment[issue])
    )

  raw_lines = ["".join(row).rstrip() for row in canvas]
  kept = [index for index, line in enumerate(raw_lines) if line]
  if not kept:
    return ()
  row_map = {old: new for new, old in enumerate(kept)}
  rendered = [raw_lines[index] for index in kept]

  if color:
    by_row: dict[int, list[tuple[int, int, str]]] = {}
    for y, start, end, lane_name in token_spans:
      by_row.setdefault(row_map[y], []).append((start, end, lane_name))
    for y, spans in by_row.items():
      line = rendered[y]
      for start, end, lane_name in sorted(spans, reverse=True):
        code = _COLORS[_lane_index(lane_name) % len(_COLORS)]
        line = (
          line[:start]
          + f"\x1b[{code}m"
          + line[start:end]
          + "\x1b[0m"
          + line[end:]
        )
      rendered[y] = line

  return tuple(rendered)


def _depths(dependencies: dict[str, tuple[str, ...]]) -> dict[str, int]:
  result: dict[str, int] = {}

  def visit(issue: str) -> int:
    if issue in result:
      return result[issue]
    deps = dependencies[issue]
    depth = 0 if not deps else 1 + max(visit(dep) for dep in deps)
    result[issue] = depth
    return depth

  for issue in sorted(dependencies, key=int):
    visit(issue)
  return result


def _metadata(root: Path, issues: tuple[str, ...]) -> dict[str, dict]:
  store = IssueMetadataStore(root)
  result: dict[str, dict] = {}
  for issue in issues:
    value = store.display_issue(int(issue))
    result[issue] = {
      "title": value.title,
      "closed": value.state == "closed",
      "link": value.link,
    }
  return result


def _color_enabled(root: Path) -> bool:
  setting = color_setting(root)
  return setting == "always" or (setting == "auto" and sys.stdout.isatty())


def _lane_index(value: str) -> int:
  result = 0
  for char in value:
    result = result * 26 + ord(char) - ord("A") + 1
  return result - 1
