from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


class DependencyMigrationManifestError(RuntimeError):
  pass


@dataclass(frozen=True)
class DependencyMigrationIssue:
  issue: int
  blocked_by: tuple[int, ...]
  provenance: tuple[str, ...]


@dataclass(frozen=True)
class DependencyMigrationManifest:
  migration_id: str
  repository: str
  issues: dict[int, DependencyMigrationIssue]
  unresolved: tuple[object, ...]


def load_dependency_migration_manifest(
  path: Path,
) -> DependencyMigrationManifest:
  try:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as error:
    raise DependencyMigrationManifestError(
      f"cannot read dependency migration manifest: {error}"
    ) from error
  return validate_dependency_migration_manifest(value)


def validate_dependency_migration_manifest(
  value: object,
) -> DependencyMigrationManifest:
  if not isinstance(value, dict):
    raise DependencyMigrationManifestError("manifest must be an object")
  required = {
    "schema_version",
    "migration_id",
    "repository",
    "semantics",
    "source_snapshot",
    "excluded_issues",
    "unresolved",
    "issues",
  }
  if set(value) != required:
    raise DependencyMigrationManifestError(
      "manifest has missing/unsupported fields"
    )
  if value["schema_version"] != 1:
    raise DependencyMigrationManifestError(
      "unsupported dependency migration manifest schema"
    )

  migration_id = _text(value["migration_id"], "migration_id")
  repository = _text(value["repository"], "repository")
  _text(value["semantics"], "semantics")

  source = value["source_snapshot"]
  if not isinstance(source, dict):
    raise DependencyMigrationManifestError("source_snapshot must be an object")
  for name in (
    "issue_count",
    "reviewed_issue_count",
    "reviewed_through_issue",
  ):
    number = source.get(name)
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
      raise DependencyMigrationManifestError(
        f"source_snapshot.{name} must be a non-negative integer"
      )
  _text(source.get("generated_from"), "source_snapshot.generated_from")

  excluded = value["excluded_issues"]
  if not isinstance(excluded, list):
    raise DependencyMigrationManifestError("excluded_issues must be an array")
  excluded_ids: set[int] = set()
  for item in excluded:
    if not isinstance(item, dict) or set(item) != {"issue", "reason"}:
      raise DependencyMigrationManifestError(
        "excluded issue must contain issue and reason"
      )
    issue = _issue_id(item["issue"], "excluded issue")
    if issue in excluded_ids:
      raise DependencyMigrationManifestError(
        f"duplicate excluded issue: {issue}"
      )
    excluded_ids.add(issue)
    _text(item["reason"], "excluded issue reason")

  unresolved = value["unresolved"]
  if not isinstance(unresolved, list):
    raise DependencyMigrationManifestError("unresolved must be an array")
  if unresolved:
    raise DependencyMigrationManifestError(
      "dependency migration manifest still has unresolved relationships"
    )

  raw_issues = value["issues"]
  if not isinstance(raw_issues, dict) or not raw_issues:
    raise DependencyMigrationManifestError("issues must be a non-empty object")

  issues: dict[int, DependencyMigrationIssue] = {}
  for key, item in raw_issues.items():
    issue = _canonical_issue_key(key)
    if issue in excluded_ids:
      raise DependencyMigrationManifestError(
        f"excluded issue appears in reviewed issues: {issue}"
      )
    if not isinstance(item, dict) or set(item) != {"blocked_by", "provenance"}:
      raise DependencyMigrationManifestError(
        f"issue {issue} must contain blocked_by and provenance"
      )
    blocked = item["blocked_by"]
    if not isinstance(blocked, list):
      raise DependencyMigrationManifestError(
        f"issue {issue} blocked_by must be an array"
      )
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in blocked:
      dependency = _issue_id(raw, f"issue {issue} dependency")
      if dependency == issue:
        raise DependencyMigrationManifestError(
          f"issue {issue} cannot depend on itself"
        )
      if dependency in seen:
        raise DependencyMigrationManifestError(
          f"issue {issue} has duplicate dependency {dependency}"
        )
      seen.add(dependency)
      normalized.append(dependency)
    if normalized != sorted(normalized):
      raise DependencyMigrationManifestError(
        f"issue {issue} dependencies must be sorted"
      )

    provenance = item["provenance"]
    if not isinstance(provenance, list) or not provenance:
      raise DependencyMigrationManifestError(
        f"issue {issue} provenance must be a non-empty array"
      )
    sources = tuple(
      _text(source, f"issue {issue} provenance")
      for source in provenance
    )
    if normalized and sources == ("reviewed:no-direct-edge",):
      raise DependencyMigrationManifestError(
        f"issue {issue} has dependencies without edge provenance"
      )
    issues[issue] = DependencyMigrationIssue(
      issue=issue,
      blocked_by=tuple(normalized),
      provenance=sources,
    )

  for issue, item in issues.items():
    for dependency in item.blocked_by:
      if dependency not in issues:
        raise DependencyMigrationManifestError(
          f"issue {issue} references unreviewed dependency {dependency}"
        )

  _reject_cycles(issues)
  if source["reviewed_issue_count"] != len(issues):
    raise DependencyMigrationManifestError(
      "reviewed_issue_count does not match manifest issue count"
    )
  if source["issue_count"] != len(issues) + len(excluded_ids):
    raise DependencyMigrationManifestError(
      "issue_count does not match reviewed plus excluded issues"
    )
  if max((*issues, *excluded_ids), default=0) != source["reviewed_through_issue"]:
    raise DependencyMigrationManifestError(
      "reviewed_through_issue does not match manifest scope"
    )

  return DependencyMigrationManifest(
    migration_id=migration_id,
    repository=repository,
    issues=issues,
    unresolved=tuple(unresolved),
  )


def _reject_cycles(issues: dict[int, DependencyMigrationIssue]) -> None:
  visiting: set[int] = set()
  complete: set[int] = set()
  path: list[int] = []

  def visit(issue: int) -> None:
    if issue in complete:
      return
    if issue in visiting:
      start = path.index(issue)
      cycle = path[start:] + [issue]
      rendered = " -> ".join(f"#{value}" for value in cycle)
      raise DependencyMigrationManifestError(
        f"dependency migration graph contains cycle: {rendered}"
      )
    visiting.add(issue)
    path.append(issue)
    for dependency in issues[issue].blocked_by:
      visit(dependency)
    path.pop()
    visiting.remove(issue)
    complete.add(issue)

  for issue in sorted(issues):
    visit(issue)


def _canonical_issue_key(value: object) -> int:
  if not isinstance(value, str) or not value.isdigit():
    raise DependencyMigrationManifestError(
      f"issue key must be a canonical decimal string: {value!r}"
    )
  issue = int(value)
  if issue <= 0 or str(issue) != value:
    raise DependencyMigrationManifestError(
      f"issue key must be a canonical positive decimal: {value!r}"
    )
  return issue


def _issue_id(value: object, name: str) -> int:
  if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
    raise DependencyMigrationManifestError(
      f"{name} must be a positive integer"
    )
  return value


def _text(value: object, name: str) -> str:
  if not isinstance(value, str) or not value.strip():
    raise DependencyMigrationManifestError(f"{name} must be non-empty text")
  return value
