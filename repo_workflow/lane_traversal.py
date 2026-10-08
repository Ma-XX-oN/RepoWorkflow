from __future__ import annotations

from dataclasses import dataclass


GROUP_KINDS = ("feature", "epic", "initiative")


class LaneTraversalError(ValueError):
  pass


def group_kind(title: str) -> str | None:
  if not isinstance(title, str):
    return None
  for kind in GROUP_KINDS:
    if title.startswith(f"{kind.title()}:"):
      return kind
  return None


@dataclass(frozen=True)
class FollowPolicy:
  group: int = 0
  feature: int = 0
  epic: int = 0
  initiative: int = 0

  def __post_init__(self) -> None:
    values = {
      "group": self.group,
      "feature": self.feature,
      "epic": self.epic,
      "initiative": self.initiative,
    }
    for name, value in values.items():
      if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LaneTraversalError(f"invalid follow budget for {name}: {value!r}")
    if self.group and any(
      getattr(self, kind)
      for kind in GROUP_KINDS
    ):
      raise LaneTraversalError(
        "combining --follow group with type-specific --follow is not "
        "defined by the current contract"
      )

  def remaining(self) -> tuple[int, int, int, int]:
    return (self.group, self.feature, self.epic, self.initiative)

  def cross(
    self,
    kind: str | None,
    remaining: tuple[int, int, int, int],
  ) -> tuple[int, int, int, int] | None:
    if kind is None:
      return remaining
    group, feature, epic, initiative = remaining
    if self.group:
      if group < 1:
        return None
      return (group - 1, feature, epic, initiative)
    index = {
      "feature": 1,
      "epic": 2,
      "initiative": 3,
    }[kind]
    values = [group, feature, epic, initiative]
    if values[index] < 1:
      return None
    values[index] -= 1
    return tuple(values)


@dataclass(frozen=True)
class TraversalState:
  issue: str
  remaining: tuple[int, int, int, int]


def parse_follow_arguments(values: list[tuple[str, str | None]]) -> FollowPolicy:
  budgets = {
    "group": 0,
    "feature": 0,
    "epic": 0,
    "initiative": 0,
  }
  for kind, raw_count in values:
    if kind not in budgets:
      raise LaneTraversalError(f"invalid --follow group kind: {kind}")
    count = 1 if raw_count is None else _positive_count(raw_count)
    if budgets[kind]:
      raise LaneTraversalError(f"duplicate --follow {kind} is not permitted")
    budgets[kind] = count
  return FollowPolicy(**budgets)


def _positive_count(value: str) -> int:
  if not isinstance(value, str) or not value.isdecimal() or int(value) < 1:
    raise LaneTraversalError(f"invalid --follow count: {value!r}")
  return int(value)
