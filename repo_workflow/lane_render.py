from __future__ import annotations

from pathlib import Path
import sys

from .lane_selection import LaneSelection, LaneSelectionStore
from .relationship_store import RelationshipStore
from .repo_info_adapter import issue_info, resolve_info_config
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
  titles: bool = True,
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

  metadata = _metadata(root, tuple(sorted(visible, key=int)), links)
  return _render_graph(
    selection,
    graph,
    visible,
    metadata,
    links=links,
    titles=titles,
    color=_color_enabled(root),
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
  positions = _positions(selection, dependencies, depths)

  columns = sorted(set(depths.values()))
  annotation_width: dict[int, int] = {}
  lane_width: dict[int, int] = {}
  issue_width: dict[int, int] = {}
  plain_labels: dict[str, str] = {}
  tokens: dict[str, str] = {}

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
    lane_name = selection.assignment[issue]
    token = (
      annotation.rjust(annotation_width[column])
      + lane_name.rjust(lane_width[column])
      + "."
      + issue.rjust(issue_width[column])
    )
    tokens[issue] = token
    label = token
    if titles and (title := metadata[issue]["title"]):
      label += f"  {title}"
    if links:
      label += f"  {metadata[issue]['link']}"
    plain_labels[issue] = label

  column_width = {
    column: max(
      len(plain_labels[issue])
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

  max_y = max(y for _, y in positions.values())
  line_bits: dict[tuple[int, int], int] = {}

  for target in sorted(visible, key=int):
    for source in dependencies[target]:
      _draw_edge(
        line_bits,
        source,
        target,
        positions,
        column_start,
        column_width,
        plain_labels,
      )

  width = max(
    column_start[depths[issue]] + len(plain_labels[issue])
    for issue in visible
  )
  height = max(
    [max_y + 1]
    + [y + 1 for _, y in line_bits]
  )
  canvas = [[" "] * width for _ in range(height)]

  for (x, y), bits in line_bits.items():
    if 0 <= y < height and 0 <= x < width:
      canvas[y][x] = _line_char(bits)

  token_spans: list[tuple[int, int, int, str]] = []
  for issue in sorted(visible, key=int):
    column, y = positions[issue]
    x = column_start[column]
    label = plain_labels[issue]
    for offset, char in enumerate(label):
      canvas[y][x + offset] = char
    token_spans.append((y, x, x + len(tokens[issue]), selection.assignment[issue]))

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
        line = line[:start] + f"\x1b[{code}m" + line[start:end] + "\x1b[0m" + line[end:]
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


def _positions(
  selection: LaneSelection,
  dependencies: dict[str, tuple[str, ...]],
  depths: dict[str, int],
) -> dict[str, tuple[int, int]]:
  result: dict[str, tuple[int, int]] = {}
  occupied: dict[int, set[int]] = {}

  for issue in sorted(dependencies, key=lambda value: (depths[value], int(value))):
    column = depths[issue]
    deps = dependencies[issue]
    used = occupied.setdefault(column, set())

    if deps:
      preferred = sorted(
        deps,
        key=lambda dependency: (
          selection.assignment[dependency] != selection.assignment[issue],
          int(dependency),
        ),
      )[0]
      y = result[preferred][1]
    else:
      y = 0
      while y in used:
        y += 2

    if y in used:
      offset = 2
      while y + offset in used:
        offset += 2
      y += offset

    used.add(y)
    result[issue] = (column, y)

  return result


def _draw_edge(
  bits: dict[tuple[int, int], int],
  source: str,
  target: str,
  positions: dict[str, tuple[int, int]],
  column_start: dict[int, int],
  column_width: dict[int, int],
  labels: dict[str, str],
) -> None:
  source_column, source_y = positions[source]
  target_column, target_y = positions[target]
  label_last = column_start[source_column] + len(labels[source]) - 1
  source_x = column_start[source_column] + column_width[source_column] + 2
  target_x = column_start[target_column] - 2

  if source_y == target_y and not _node_between(
    source,
    target,
    positions,
    source_y,
  ):
    _horizontal(bits, label_last + 2, column_start[target_column] - 1, source_y)
    return

  _horizontal(bits, label_last + 2, source_x, source_y)
  track_y = source_y + 1 if source_y <= target_y else source_y - 1
  if track_y < 0:
    track_y = source_y + 1

  _vertical(bits, source_x, source_y, track_y)
  _horizontal(bits, source_x, target_x, track_y)
  _vertical(bits, target_x, track_y, target_y)
  _horizontal(bits, target_x, column_start[target_column] - 1, target_y)


def _node_between(
  source: str,
  target: str,
  positions: dict[str, tuple[int, int]],
  row: int,
) -> bool:
  source_column = positions[source][0]
  target_column = positions[target][0]
  return any(
    y == row and source_column < column < target_column
    for issue, (column, y) in positions.items()
    if issue not in {source, target}
  )


_L = 1
_R = 2
_U = 4
_D = 8


def _horizontal(bits: dict[tuple[int, int], int], x1: int, x2: int, y: int) -> None:
  if x2 < x1:
    x1, x2 = x2, x1
  if x1 == x2:
    bits[(x1, y)] = bits.get((x1, y), 0) | _L | _R
    return
  for x in range(x1, x2 + 1):
    value = 0
    if x > x1:
      value |= _L
    if x < x2:
      value |= _R
    bits[(x, y)] = bits.get((x, y), 0) | value


def _vertical(bits: dict[tuple[int, int], int], x: int, y1: int, y2: int) -> None:
  if y2 < y1:
    y1, y2 = y2, y1
  if y1 == y2:
    bits[(x, y1)] = bits.get((x, y1), 0) | _U | _D
    return
  for y in range(y1, y2 + 1):
    value = 0
    if y > y1:
      value |= _U
    if y < y2:
      value |= _D
    bits[(x, y)] = bits.get((x, y), 0) | value


def _line_char(bits: int) -> str:
  mapping = {
    _L: "─",
    _R: "─",
    _L | _R: "─",
    _U: "│",
    _D: "│",
    _U | _D: "│",
    _R | _D: "┌",
    _L | _D: "┐",
    _R | _U: "└",
    _L | _U: "┘",
    _R | _U | _D: "├",
    _L | _U | _D: "┤",
    _L | _R | _D: "┬",
    _L | _R | _U: "┴",
    _L | _R | _U | _D: "┼",
  }
  return mapping.get(bits, "─")


def _metadata(root: Path, issues: tuple[str, ...], links: bool) -> dict[str, dict]:
  config = resolve_info_config(root)
  result: dict[str, dict] = {}
  for issue in issues:
    value = issue_info(root, config, int(issue))
    result[issue] = {
      "title": value["title"],
      "closed": value["state"] == "closed",
      "link": value["link"],
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
