from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .relationships import RelationshipGraph, RelationshipSchemaError


@dataclass(frozen=True)
class Lane:
  name: str
  issues: tuple[str, ...]


@dataclass(frozen=True)
class LanePlan:
  selected: tuple[str, ...]
  closure: tuple[str, ...]
  lanes: tuple[Lane, ...]

  def owner(self, issue: str | int) -> str:
    key = str(int(issue))
    for lane in self.lanes:
      if key in lane.issues:
        return lane.name
    raise KeyError(key)


def dependency_component(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
) -> tuple[str, ...]:
  selected_ids = _ids(selected)
  for issue in selected_ids:
    graph.issue(issue)

  neighbours = {issue: set() for issue in graph.issues}
  for issue, relation in graph.issues.items():
    for dependency in relation.depends_on:
      neighbours[issue].add(dependency)
      neighbours[dependency].add(issue)

  connected: set[str] = set()
  pending = list(selected_ids)
  while pending:
    issue = pending.pop(0)
    if issue in connected:
      continue
    connected.add(issue)
    pending.extend(sorted(
      (value for value in neighbours[issue] if value not in connected),
      key=int,
    ))
  return tuple(sorted(connected, key=int))


def decompose_lanes(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  completed: Iterable[str | int] = (),
) -> LanePlan:
  selected_ids = _ids(selected)
  completed_ids = set(_ids(completed))
  closure = set(dependency_component(graph, selected_ids)) - completed_ids

  if not closure:
    return LanePlan(selected_ids, (), ())

  # Deterministic topological order: dependencies before dependants, with a
  # numeric tie-break.
  indegree = {issue: 0 for issue in closure}
  dependants = {issue: [] for issue in closure}
  for issue in closure:
    for dependency in graph.issue(issue).depends_on:
      if dependency in closure:
        indegree[issue] += 1
        dependants[dependency].append(issue)
  ready = sorted((i for i, degree in indegree.items() if degree == 0), key=int)
  order: list[str] = []
  while ready:
    issue = ready.pop(0)
    order.append(issue)
    for dependant in sorted(dependants[issue], key=int):
      indegree[dependant] -= 1
      if indegree[dependant] == 0:
        ready.append(dependant)
        ready.sort(key=int)
  if len(order) != len(closure):
    raise RelationshipSchemaError("direct dependency graph is cyclic")

  owners: dict[str, int] = {}
  lane_issues: list[list[str]] = []
  for issue in order:
    predecessors = sorted(
      (
        dependency
        for dependency in graph.issue(issue).depends_on
        if dependency in closure
      ),
      key=int,
    )
    extendable = [
      predecessor
      for predecessor in predecessors
      if lane_issues[owners[predecessor]][-1] == predecessor
    ]
    if extendable:
      # A lane is a path, so only its current tail may be extended.  At a
      # convergence choose the smallest eligible predecessor deterministically.
      chosen = min(extendable, key=int)
      lane_index = owners[chosen]
    else:
      # Roots and additional branches begin new lanes.  This prevents one lane
      # from containing siblings that do not form a direct path.
      lane_index = len(lane_issues)
      lane_issues.append([])
    owners[issue] = lane_index
    lane_issues[lane_index].append(issue)

  lanes = tuple(
    Lane(_lane_name(index), tuple(issues))
    for index, issues in enumerate(lane_issues)
    if issues
  )
  return LanePlan(
    selected=selected_ids,
    closure=tuple(sorted(closure, key=int)),
    lanes=lanes,
  )


def _ids(values: Iterable[str | int]) -> tuple[str, ...]:
  result: set[str] = set()
  for value in values:
    if isinstance(value, bool):
      raise ValueError(f"invalid issue id: {value!r}")
    text = str(value)
    if not text.isdigit() or int(text) <= 0:
      raise ValueError(f"invalid issue id: {value!r}")
    result.add(str(int(text)))
  return tuple(sorted(result, key=int))


def _lane_name(index: int) -> str:
  # Spreadsheet-style stable labels: A..Z, AA..AZ, BA...
  value = index + 1
  chars: list[str] = []
  while value:
    value, remainder = divmod(value - 1, 26)
    chars.append(chr(ord("A") + remainder))
  return "".join(reversed(chars))
