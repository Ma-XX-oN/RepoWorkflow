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


def decompose_lanes(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  completed: Iterable[str | int] = (),
) -> LanePlan:
  selected_ids = _ids(selected)
  completed_ids = set(_ids(completed))
  for issue in selected_ids:
    graph.issue(issue)

  closure: set[str] = set()
  visiting: set[str] = set()

  def include(issue: str) -> None:
    if issue in completed_ids or issue in closure:
      return
    if issue in visiting:
      raise RelationshipSchemaError(f"direct dependency cycle includes issue {issue}")
    visiting.add(issue)
    relation = graph.issue(issue)
    for dependency in relation.depends_on:
      include(dependency)
    visiting.remove(issue)
    closure.add(issue)

  for issue in selected_ids:
    include(issue)

  if not closure:
    return LanePlan(selected_ids, (), ())

  # Deterministic topological order: dependencies before dependants, numeric tie-break.
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
    predecessors = [
      dependency
      for dependency in graph.issue(issue).depends_on
      if dependency in closure
    ]
    if not predecessors:
      lane_index = len(lane_issues)
      lane_issues.append([])
    else:
      # Convergence belongs to exactly one predecessor lane.  Pick the lane
      # whose owned predecessor has the smallest issue ID; this is stable and
      # independent of dict/input ordering.
      chosen = min(predecessors, key=int)
      lane_index = owners[chosen]
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
