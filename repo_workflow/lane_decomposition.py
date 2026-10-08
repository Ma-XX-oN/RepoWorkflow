from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .lane_traversal import (
  FollowPolicy,
  ShowChildrenPolicy,
  TraversalState,
  dependant_boundary_kind,
  group_kind,
)
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


@dataclass(frozen=True)
class _Discovery:
  dependency_states: tuple[TraversalState, ...]
  dependant_states: tuple[TraversalState, ...]
  stopped_dependency_groups: tuple[TraversalState, ...]
  stopped_dependant_groups: tuple[TraversalState, ...]


def dependency_states(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  follow: FollowPolicy | None = None,
) -> tuple[TraversalState, ...]:
  discovery = _discover(graph, selected, follow=follow)
  return tuple(sorted(
    set(discovery.dependency_states) | set(discovery.dependant_states),
    key=lambda state: (int(state.issue), state.remaining),
  ))


def dependency_component(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  follow: FollowPolicy | None = None,
  show_children: ShowChildrenPolicy | None = None,
) -> tuple[str, ...]:
  policy = FollowPolicy() if follow is None else follow
  context = ShowChildrenPolicy() if show_children is None else show_children
  discovery = _discover(graph, selected, follow=policy)
  visible = {
    state.issue
    for state in (
      *discovery.dependency_states,
      *discovery.dependant_states,
    )
  }

  for state in discovery.stopped_dependency_groups:
    kind = group_kind(graph.issue(state.issue).title)
    if context.matches(kind):
      visible.update(graph.issue(state.issue).depends_on)

  dependants = _dependants(graph)
  for state in discovery.stopped_dependant_groups:
    kind = group_kind(graph.issue(state.issue).title)
    if context.matches(kind):
      visible.update(dependants[state.issue])

  return tuple(sorted(visible, key=int))


def _discover(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  follow: FollowPolicy | None = None,
) -> _Discovery:
  selected_ids = _ids(selected)
  selected_set = set(selected_ids)
  for issue in selected_ids:
    graph.issue(issue)
  policy = FollowPolicy() if follow is None else follow

  dependency_visited: set[TraversalState] = set()
  stopped_dependency_groups: set[TraversalState] = set()
  terminals: set[TraversalState] = set()
  pending = [
    TraversalState(issue, policy.remaining())
    for issue in selected_ids
  ]

  while pending:
    state = pending.pop(0)
    if state in dependency_visited:
      continue
    dependency_visited.add(state)

    remaining = state.remaining
    kind = group_kind(graph.issue(state.issue).title)
    if state.issue not in selected_set:
      crossed = policy.cross(kind, remaining)
      if crossed is None:
        stopped_dependency_groups.add(state)
        terminals.add(state)
        continue
      remaining = crossed

    dependencies = graph.issue(state.issue).depends_on
    if not dependencies:
      terminals.add(TraversalState(state.issue, remaining))
      continue

    for dependency in dependencies:
      next_state = TraversalState(dependency, remaining)
      if next_state not in dependency_visited and next_state not in pending:
        pending.append(next_state)

  dependants = _dependants(graph)
  dependant_visited: set[TraversalState] = set()
  stopped_dependant_groups: set[TraversalState] = set()
  pending_right: list[tuple[TraversalState, bool]] = []

  for terminal in sorted(
    terminals,
    key=lambda state: (int(state.issue), state.remaining),
  ):
    if terminal in stopped_dependency_groups:
      continue
    title = graph.issue(terminal.issue).title
    if (
      terminal.issue not in selected_set
      and dependant_boundary_kind(title) is not None
    ):
      continue
    pending_right.append((terminal, False))

  while pending_right:
    state, cross_current = pending_right.pop(0)
    if state in dependant_visited:
      continue
    dependant_visited.add(state)

    remaining = state.remaining
    if cross_current and state.issue not in selected_set:
      kind = group_kind(graph.issue(state.issue).title)
      crossed = policy.cross(kind, remaining)
      if crossed is None:
        stopped_dependant_groups.add(state)
        continue
      remaining = crossed

    for dependant in dependants[state.issue]:
      next_state = TraversalState(dependant, remaining)
      if (
        next_state not in dependant_visited
        and all(item[0] != next_state for item in pending_right)
      ):
        pending_right.append((next_state, True))

  return _Discovery(
    dependency_states=tuple(sorted(
      dependency_visited,
      key=lambda state: (int(state.issue), state.remaining),
    )),
    dependant_states=tuple(sorted(
      dependant_visited,
      key=lambda state: (int(state.issue), state.remaining),
    )),
    stopped_dependency_groups=tuple(sorted(
      stopped_dependency_groups,
      key=lambda state: (int(state.issue), state.remaining),
    )),
    stopped_dependant_groups=tuple(sorted(
      stopped_dependant_groups,
      key=lambda state: (int(state.issue), state.remaining),
    )),
  )


def _dependants(graph: RelationshipGraph) -> dict[str, tuple[str, ...]]:
  values: dict[str, list[str]] = {
    issue: []
    for issue in graph.issues
  }
  for issue, relation in graph.issues.items():
    for dependency in relation.depends_on:
      values[dependency].append(issue)
  return {
    issue: tuple(sorted(items, key=int))
    for issue, items in values.items()
  }


def decompose_lanes(
  graph: RelationshipGraph,
  selected: Iterable[str | int],
  *,
  completed: Iterable[str | int] = (),
  follow: FollowPolicy | None = None,
  show_children: ShowChildrenPolicy | None = None,
) -> LanePlan:
  selected_ids = _ids(selected)
  completed_ids = set(_ids(completed))
  closure = set(
    dependency_component(
      graph,
      selected_ids,
      follow=follow,
      show_children=show_children,
    )
  ) - completed_ids

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
