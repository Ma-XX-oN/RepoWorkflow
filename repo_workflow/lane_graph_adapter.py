from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re

from .graph_render_model import (
  AlignedColumn,
  ColourFunction,
  FormatEntry,
  Graph,
  GraphSiblings,
  Lane,
)
from .lane_selection import LaneSelection


_LABEL = re.compile(r"^([*○●◎✓♥✕?]*)(?:(I|E|F):)?([A-Z]+)([0-9]+)$")
_STATE_GLYPHS = {
  "not_started": "○",
  "active": "●",
  "in_review": "◎",
  "accepted": "✓",
  "completed": "♥",
  "aborted": "✕",
}
_TYPE_PREFIXES = {
  "Initiative:": "I:",
  "Epic:": "E:",
  "Feature:": "F:",
}


class LaneGraphProjectionError(RuntimeError):
  pass


@dataclass(frozen=True)
class LaneGraphProjection:
  graph: Graph
  issue_text: dict[str, str]


def project_lane_graph(
  selection: LaneSelection,
  relationship_graph,
  visible: set[str],
  metadata: dict[str, dict],
  *,
  lane_colours: dict[str, ColourFunction],
  default_edge_colour: ColourFunction,
  display_width: Callable[[str], int],
) -> LaneGraphProjection:
  if not visible:
    return LaneGraphProjection(
      Graph((), (), default_edge_colour, make_lane_formatter(display_width)),
      {},
    )

  missing = visible - set(selection.assignment)
  if missing:
    raise LaneGraphProjectionError(
      "visible nodes are missing lane assignment: "
      + ", ".join(sorted(missing, key=int))
    )

  issue_text = {
    issue: _raw_label(selection, issue, metadata)
    for issue in sorted(visible, key=int)
  }
  full_outgoing = {issue: set() for issue in visible}
  for target in visible:
    for source in relationship_graph.issue(target).depends_on:
      if source not in visible:
        continue
      full_outgoing[source].add(target)

  full_incoming = {issue: set() for issue in visible}
  for source, targets in full_outgoing.items():
    for target in targets:
      full_incoming[target].add(source)

  lane_names = sorted(
    {selection.assignment[issue] for issue in visible},
    key=_lane_key,
  )
  lane_orders: dict[str, tuple[str, ...]] = {}
  protected_edges: set[tuple[str, str]] = set()
  for lane_name in lane_names:
    issues = {
      issue
      for issue in visible
      if selection.assignment[issue] == lane_name
    }
    ordered = _lane_path(issues, full_outgoing, full_incoming)
    lane_orders[lane_name] = ordered
    protected_edges.update(zip(ordered, ordered[1:]))

  outgoing = _transitive_reduction(full_outgoing, protected_edges)
  incoming = {issue: set() for issue in visible}
  for source, targets in outgoing.items():
    for target in targets:
      incoming[target].add(source)

  buckets: dict[tuple, list[str]] = {}
  isolated: list[str] = []
  for issue in sorted(visible, key=int):
    signature = (
      tuple(sorted(outgoing[issue], key=int)),
      tuple(sorted(incoming[issue], key=int)),
    )
    if not outgoing[issue] and not incoming[issue]:
      isolated.append(issue)
    else:
      buckets.setdefault(signature, []).append(issue)

  groups: list[GraphSiblings] = []
  issue_group: dict[str, GraphSiblings] = {}
  for issues in buckets.values():
    group = GraphSiblings(
      tuple(issue_text[issue] for issue in sorted(issues, key=int))
    )
    groups.append(group)
    for issue in issues:
      issue_group[issue] = group
  for issue in isolated:
    group = GraphSiblings((issue_text[issue],))
    groups.append(group)
    issue_group[issue] = group

  for group in groups:
    group_issues = [
      issue
      for issue, candidate in issue_group.items()
      if candidate is group
    ]
    targets = {
      issue_group[target]
      for issue in group_issues
      for target in outgoing[issue]
    }
    group.to_nodes = tuple(sorted(targets, key=_group_key))

  lanes: list[Lane] = []
  for lane_name in lane_names:
    if lane_name not in lane_colours:
      raise LaneGraphProjectionError(
        f"missing colour function for lane {lane_name}"
      )
    ordered = lane_orders[lane_name]
    lanes.append(
      Lane(
        tuple(issue_text[issue] for issue in ordered),
        lane_colours[lane_name],
      )
    )

  return LaneGraphProjection(
    Graph(
      tuple(sorted(groups, key=_group_key)),
      tuple(lanes),
      default_edge_colour,
      make_lane_formatter(display_width),
    ),
    issue_text,
  )


def make_lane_formatter(
  display_width: Callable[[str], int],
):
  def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
    if not entries:
      return AlignedColumn((), 0)
    parsed = [_parse_label(entry.raw_text) for entry in entries]
    annotation_width = max(display_width(item[0]) for item in parsed)
    type_width = 2 if any(item[1] for item in parsed) else 0
    lane_width = max(display_width(item[2]) for item in parsed)
    issue_width = max(display_width(item[3]) for item in parsed)

    strings: list[str] = []
    for entry, (annotation, kind, lane, issue) in zip(entries, parsed):
      annotation_text = _pad_left(
        annotation,
        annotation_width,
        display_width,
      )
      type_text = _pad_left(
        f"{kind}:" if kind else "",
        type_width,
        display_width,
      )
      data_text = (
        type_text
        + _pad_left(lane, lane_width, display_width)
        + _pad_left(issue, issue_width, display_width)
      )
      strings.append(annotation_text + entry.colour(data_text))

    width = annotation_width + type_width + lane_width + issue_width
    return AlignedColumn(tuple(strings), width)

  return formatter


def _raw_label(
  selection: LaneSelection,
  issue: str,
  metadata: dict[str, dict],
) -> str:
  state = metadata[issue].get("lifecycle_state")
  if state is not None and state not in _STATE_GLYPHS:
    raise LaneGraphProjectionError(f"unsupported lifecycle state: {state!r}")
  annotation = (
    ("*" if issue in set(selection.roots) else "")
    + _STATE_GLYPHS.get(state, "?")
  )
  kind = _type_prefix(metadata[issue]["title"])
  return f"{annotation}{kind}{selection.assignment[issue]}{issue}"


def _type_prefix(title: str) -> str:
  for prefix, annotation in _TYPE_PREFIXES.items():
    if title.startswith(prefix):
      return annotation
  return ""


def _parse_label(value: str) -> tuple[str, str, str, str]:
  match = _LABEL.fullmatch(value)
  if match is None:
    raise LaneGraphProjectionError(
      f"unsupported RepoWorkflow graph label: {value!r}"
    )
  return (
    match.group(1),
    match.group(2) or "",
    match.group(3),
    match.group(4),
  )


def _pad_left(
  value: str,
  width: int,
  display_width: Callable[[str], int],
) -> str:
  padding = width - display_width(value)
  if padding < 0:
    raise LaneGraphProjectionError("display width function is inconsistent")
  return " " * padding + value


def _transitive_reduction(
  outgoing: dict[str, set[str]],
  protected_edges: set[tuple[str, str]],
) -> dict[str, set[str]]:
  reduced = {
    source: set(targets)
    for source, targets in outgoing.items()
  }
  for source in sorted(outgoing, key=int):
    for target in sorted(outgoing[source], key=int):
      if (
        (source, target) not in protected_edges
        and _has_alternate_path(
          source,
          target,
          outgoing,
        )
      ):
        reduced[source].discard(target)
  return reduced


def _has_alternate_path(
  source: str,
  target: str,
  outgoing: dict[str, set[str]],
) -> bool:
  pending = [
    node
    for node in sorted(outgoing[source], key=int, reverse=True)
    if node != target
  ]
  seen: set[str] = set()
  while pending:
    node = pending.pop()
    if node == target:
      return True
    if node in seen:
      continue
    seen.add(node)
    pending.extend(
      candidate
      for candidate in sorted(
        outgoing[node],
        key=int,
        reverse=True,
      )
      if candidate not in seen
    )
  return False


def _lane_path(
  issues: set[str],
  outgoing: dict[str, set[str]],
  incoming: dict[str, set[str]],
) -> tuple[str, ...]:
  indegree = {
    issue: len(incoming[issue] & issues)
    for issue in issues
  }
  ready = sorted(
    (issue for issue, value in indegree.items() if value == 0),
    key=int,
  )
  order: list[str] = []
  while ready:
    issue = ready.pop(0)
    order.append(issue)
    for target in sorted(outgoing[issue] & issues, key=int):
      indegree[target] -= 1
      if indegree[target] == 0:
        ready.append(target)
        ready.sort(key=int)
  if len(order) != len(issues):
    raise LaneGraphProjectionError("lane assignment contains a cycle")
  for source, target in zip(order, order[1:]):
    if target not in outgoing[source]:
      raise LaneGraphProjectionError(
        f"lane omits an intermediate path node: {source} -> {target}"
      )
  return tuple(order)


def _group_key(group: GraphSiblings) -> tuple[str, ...]:
  return tuple(sorted(group.nodes))


def _lane_key(value: str) -> int:
  result = 0
  for char in value:
    if not ("A" <= char <= "Z"):
      raise LaneGraphProjectionError(f"invalid lane name: {value!r}")
    result = result * 26 + ord(char) - ord("A") + 1
  return result
