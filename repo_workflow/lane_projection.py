from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .relationships import RelationshipGraph


PROJECTION_MODES = frozenset({
  "both",
  "dependencies",
  "dependents",
  "single",
})


class LaneProjectionError(ValueError):
  pass


@dataclass(frozen=True, order=True)
class ProjectionRule:
  seed: str
  mode: str = "both"

  def __post_init__(self) -> None:
    seed = _issue_id(self.seed)
    if self.mode not in PROJECTION_MODES:
      raise LaneProjectionError(f"invalid projection mode: {self.mode!r}")
    object.__setattr__(self, "seed", seed)

  def to_json_value(self) -> dict[str, str]:
    return {"seed": self.seed, "mode": self.mode}

  @classmethod
  def from_json_value(cls, value: object) -> "ProjectionRule":
    if not isinstance(value, dict) or set(value) != {"seed", "mode"}:
      raise LaneProjectionError("projection rule must contain seed and mode")
    return cls(value["seed"], value["mode"])


def project_rule(
  graph: RelationshipGraph,
  rule: ProjectionRule,
) -> frozenset[str]:
  graph.issue(rule.seed)
  if rule.mode == "single":
    return frozenset({rule.seed})
  if rule.mode == "dependencies":
    return _dependencies(graph, rule.seed)
  if rule.mode == "dependents":
    return _dependents(graph, rule.seed)
  return _dependencies(graph, rule.seed) | _dependents(graph, rule.seed)


def project_rules(
  graph: RelationshipGraph,
  includes: Iterable[ProjectionRule],
  excludes: Iterable[ProjectionRule] = (),
) -> tuple[str, ...]:
  include_set: set[str] = set()
  for rule in _rules(includes):
    include_set.update(project_rule(graph, rule))

  exclude_set: set[str] = set()
  for rule in _rules(excludes):
    exclude_set.update(project_rule(graph, rule))

  return tuple(sorted(include_set - exclude_set, key=int))


def normalize_rules(
  rules: Iterable[ProjectionRule],
) -> tuple[ProjectionRule, ...]:
  return tuple(sorted(set(_rules(rules)), key=_rule_key))


def _dependencies(
  graph: RelationshipGraph,
  seed: str,
) -> frozenset[str]:
  visited: set[str] = set()
  pending = [seed]
  while pending:
    issue = pending.pop()
    if issue in visited:
      continue
    visited.add(issue)
    pending.extend(
      dependency
      for dependency in reversed(graph.issue(issue).depends_on)
      if dependency not in visited
    )
  return frozenset(visited)


def _dependents(
  graph: RelationshipGraph,
  seed: str,
) -> frozenset[str]:
  dependents: dict[str, list[str]] = {
    issue: []
    for issue in graph.issues
  }
  for issue, relation in graph.issues.items():
    for dependency in relation.depends_on:
      dependents[dependency].append(issue)

  visited: set[str] = set()
  pending = [seed]
  while pending:
    issue = pending.pop()
    if issue in visited:
      continue
    visited.add(issue)
    pending.extend(
      dependant
      for dependant in sorted(dependents[issue], key=int, reverse=True)
      if dependant not in visited
    )
  return frozenset(visited)


def _rules(values: Iterable[ProjectionRule]) -> tuple[ProjectionRule, ...]:
  result: list[ProjectionRule] = []
  for value in values:
    if not isinstance(value, ProjectionRule):
      raise LaneProjectionError(
        f"projection rule must be ProjectionRule, got {type(value).__name__}"
      )
    result.append(value)
  return tuple(result)


def _rule_key(rule: ProjectionRule) -> tuple[int, str]:
  return (int(rule.seed), rule.mode)


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise LaneProjectionError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1:
    raise LaneProjectionError(f"invalid issue id: {value!r}")
  return str(int(text))
