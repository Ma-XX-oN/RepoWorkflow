from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git import git
from .lane_projection import ProjectionRule, normalize_rules
from .state_store import JsonRecordStore, StateStoreError, WriterIdentity


RECORD_KEY = "coverage"


@dataclass(frozen=True)
class RelationshipCoverage:
  partial: bool
  rules: tuple[ProjectionRule, ...]


class RelationshipCoverageStore:
  def __init__(self, root: Path):
    root = Path(root).resolve()
    git_dir = Path(git(root, "rev-parse", "--git-dir").stdout.strip())
    if not git_dir.is_absolute():
      git_dir = (root / git_dir).resolve()
    self.records = JsonRecordStore(
      git_dir / "repoworkflow" / "lane-relationship-coverage"
    )

  def read(self) -> tuple[RelationshipCoverage | None, int | None]:
    try:
      record = self.records.read(RECORD_KEY)
    except StateStoreError as error:
      if "record is missing:" in str(error):
        return None, None
      raise
    value = record["value"]
    if not isinstance(value, dict) or set(value) != {"partial", "rules"}:
      raise StateStoreError("invalid lane relationship coverage")
    partial = value["partial"]
    if not isinstance(partial, bool):
      raise StateStoreError("invalid lane relationship coverage partial flag")
    raw_rules = value["rules"]
    if not isinstance(raw_rules, list):
      raise StateStoreError("invalid lane relationship coverage rules")
    rules = normalize_rules(
      tuple(ProjectionRule.from_json_value(item) for item in raw_rules)
    )
    return RelationshipCoverage(partial, rules), record["revision"]

  def write(
    self,
    coverage: RelationshipCoverage,
    writer: WriterIdentity,
    *,
    expected_revision: int | None,
  ) -> None:
    value = {
      "partial": coverage.partial,
      "rules": [rule.to_json_value() for rule in normalize_rules(coverage.rules)],
    }
    if expected_revision is None:
      self.records.create(RECORD_KEY, value, writer)
    else:
      self.records.replace(RECORD_KEY, expected_revision, value, writer)


def rule_is_covered(
  coverage: RelationshipCoverage,
  rule: ProjectionRule,
) -> bool:
  if not coverage.partial:
    return True
  modes = {
    item.mode
    for item in coverage.rules
    if item.seed == rule.seed
  }
  if rule.mode == "single":
    return bool(modes)
  if rule.mode == "dependencies":
    return "dependencies" in modes or "both" in modes
  if rule.mode == "dependents":
    return "dependents" in modes or "both" in modes
  return "both" in modes or (
    "dependencies" in modes and "dependents" in modes
  )
