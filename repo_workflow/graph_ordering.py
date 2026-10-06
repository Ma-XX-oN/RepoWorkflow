from __future__ import annotations

from .graph_render_model import (
  GraphSiblings,
  ValidatedGraph,
)
from .graph_render_types import Placement


def group_key(group: GraphSiblings) -> tuple[str, ...]:
  return tuple(sorted(group.nodes))


def group_ranks(
  groups: tuple[GraphSiblings, ...],
) -> dict[GraphSiblings, int]:
  incoming: dict[GraphSiblings, set[GraphSiblings]] = {
    group: set() for group in groups
  }
  for group in groups:
    for target in group.to_nodes:
      incoming[target].add(group)

  indegree = {group: len(incoming[group]) for group in groups}
  ready = sorted(
    (group for group in groups if indegree[group] == 0),
    key=group_key,
  )
  ranks = {group: 0 for group in ready}
  seen: list[GraphSiblings] = []
  while ready:
    group = ready.pop(0)
    seen.append(group)
    for target in sorted(group.to_nodes, key=group_key):
      ranks[target] = max(
        ranks.get(target, 0),
        ranks[group] + 1,
      )
      indegree[target] -= 1
      if indegree[target] == 0:
        ready.append(target)
        ready.sort(key=group_key)
  if len(seen) != len(groups):
    raise ValueError(
      "validated graph unexpectedly contains a cycle"
    )
  return ranks


def place_nodes(
  validated: ValidatedGraph,
  ranks: dict[GraphSiblings, int],
) -> tuple[
  dict[str, Placement],
  dict[int, tuple[str, ...]],
  int,
]:
  groups = validated.graph.siblings
  by_column: dict[int, list[GraphSiblings]] = {}
  connected = {
    group
    for group in groups
    if group.to_nodes
  }
  for group in groups:
    for target in group.to_nodes:
      connected.add(target)
    by_column.setdefault(ranks[group], []).append(group)

  lane_predecessor: dict[str, str] = {}
  for lane in validated.graph.lanes:
    for source, target in zip(lane.nodes, lane.nodes[1:]):
      lane_predecessor[target] = source

  placements: dict[str, Placement] = {}
  column_nodes: dict[int, tuple[str, ...]] = {}
  max_row = 0
  for column in sorted(by_column):
    ordered_groups = sorted(by_column[column], key=group_key)
    if placements:
      ordered_groups = _improve_group_order(
        ordered_groups,
        placements,
        validated,
        lane_predecessor,
        connected,
      )

    row = 0
    ordered_nodes: list[str] = []
    previous = None
    for group in ordered_groups:
      if (
        previous is not None
        and (previous in connected or group in connected)
      ):
        row += 1
      for node in sorted(group.nodes):
        placements[node] = Placement(column, row)
        ordered_nodes.append(node)
        max_row = max(max_row, row)
        row += 1
      previous = group
    column_nodes[column] = tuple(ordered_nodes)
  return placements, column_nodes, max_row


def _improve_group_order(
  groups: list[GraphSiblings],
  placements: dict[str, Placement],
  validated: ValidatedGraph,
  lane_predecessor: dict[str, str],
  connected: set[GraphSiblings],
) -> list[GraphSiblings]:
  ordered = sorted(
    groups,
    key=lambda group: (
      _group_anchor(
        group,
        placements,
        validated,
        lane_predecessor,
      ),
      group_key(group),
    ),
  )
  if len(ordered) < 2:
    return ordered

  limit = len(ordered) * len(ordered)
  for _ in range(limit):
    changed = False
    before = _group_order_cost(
      ordered,
      placements,
      validated,
      connected,
    )
    for index in range(len(ordered) - 1):
      candidate = list(ordered)
      candidate[index], candidate[index + 1] = (
        candidate[index + 1],
        candidate[index],
      )
      score = _group_order_cost(
        candidate,
        placements,
        validated,
        connected,
      )
      if score < before:
        ordered = candidate
        changed = True
        break
    if not changed:
      break
  return ordered


def _group_anchor(
  group: GraphSiblings,
  placements: dict[str, Placement],
  validated: ValidatedGraph,
  lane_predecessor: dict[str, str],
) -> tuple[int, float]:
  lane_rows = [
    placements[predecessor].row
    for node in group.nodes
    for predecessor in [lane_predecessor.get(node)]
    if predecessor in placements
  ]
  if lane_rows:
    return 0, sum(lane_rows) / len(lane_rows)

  incoming_rows = [
    placements[source].row
    for node in group.nodes
    for source in validated.incoming[node]
    if source in placements
  ]
  if incoming_rows:
    return 1, sum(incoming_rows) / len(incoming_rows)
  return 2, float("inf")


def _group_order_cost(
  groups: list[GraphSiblings],
  placements: dict[str, Placement],
  validated: ValidatedGraph,
  connected: set[GraphSiblings],
) -> tuple[int, tuple[tuple[str, ...], ...]]:
  rows: dict[str, int] = {}
  row = 0
  previous = None
  for group in groups:
    if (
      previous is not None
      and (previous in connected or group in connected)
    ):
      row += 1
    for node in sorted(group.nodes):
      rows[node] = row
      row += 1
    previous = group

  distance = 0
  for target, target_row in rows.items():
    for source in validated.incoming[target]:
      if source in placements:
        distance += abs(placements[source].row - target_row)

  return distance, tuple(group_key(group) for group in groups)
