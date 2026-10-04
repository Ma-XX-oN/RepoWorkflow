from __future__ import annotations

from dataclasses import dataclass


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1


class RelationshipSchemaError(ValueError):
  """Raised when relationship graph data violates the schema contract."""


@dataclass(frozen=True)
class IssueRelationships:
  umbrella: str | None
  shared_umbrellas: tuple[str, ...]
  depends_on: tuple[str, ...]
  umbrella_depends_on: tuple[str, ...]
  parent: str | None

  def to_json_value(self) -> dict:
    return {
      "umbrella": self.umbrella,
      "shared_umbrellas": list(self.shared_umbrellas),
      "depends_on": list(self.depends_on),
      "umbrella_depends_on": list(self.umbrella_depends_on),
      "parent": self.parent,
    }


@dataclass(frozen=True)
class RelationshipGraph:
  issues: dict[str, IssueRelationships]
  schema_version: int = SCHEMA_VERSION

  @classmethod
  def from_json_value(cls, value: dict) -> "RelationshipGraph":
    if not isinstance(value, dict):
      raise RelationshipSchemaError("relationship graph must be an object")
    version = value.get("schema_version")
    if version != SCHEMA_VERSION:
      raise RelationshipSchemaError(
        f"unsupported relationship schema version: {version!r}"
      )
    raw_issues = value.get("issues")
    if not isinstance(raw_issues, dict):
      raise RelationshipSchemaError("issues must be an object")

    issues: dict[str, IssueRelationships] = {}
    for raw_issue_id, raw in raw_issues.items():
      issue_id = _issue_id(raw_issue_id)
      if not isinstance(raw, dict):
        raise RelationshipSchemaError(
          f"issue {issue_id}: relationship record must be an object"
        )
      issues[issue_id] = _parse_issue(issue_id, raw)

    _validate_direct_dependencies(issues)
    return cls(issues=issues, schema_version=version)

  def issue(self, issue_id: str | int) -> IssueRelationships:
    key = _issue_id(issue_id)
    try:
      return self.issues[key]
    except KeyError as error:
      raise RelationshipSchemaError(f"unknown issue: {key}") from error

  def to_json_value(self) -> dict:
    return {
      "schema_version": self.schema_version,
      "issues": {
        issue_id: self.issues[issue_id].to_json_value()
        for issue_id in _sorted_issue_ids(self.issues)
      },
    }


def legacy_relationships(value: dict) -> dict[str, dict]:
  """Validate schema-v1 structure and return normalized legacy records."""
  if not isinstance(value, dict) or value.get("schema_version") != 1:
    version = value.get("schema_version") if isinstance(value, dict) else None
    raise RelationshipSchemaError(
      f"unsupported legacy relationship schema version: {version!r}"
    )
  raw_issues = value.get("issues")
  if not isinstance(raw_issues, dict):
    raise RelationshipSchemaError("issues must be an object")
  normalized: dict[str, dict] = {}
  expected = {
    "umbrella",
    "shared_umbrellas",
    "depends_on",
    "umbrella_depends_on",
    "branch_base",
    "integration_target",
  }
  for raw_issue_id, raw in raw_issues.items():
    issue_id = _issue_id(raw_issue_id)
    if not isinstance(raw, dict) or set(raw) != expected:
      raise RelationshipSchemaError(
        f"issue {issue_id}: legacy relationship fields are invalid"
      )
    normalized[issue_id] = dict(raw)
  return normalized


def ready_issues(
  graph: RelationshipGraph,
  completed: set[str | int],
) -> tuple[str, ...]:
  """Return incomplete issues whose direct leaf dependencies are complete."""
  done = {_issue_id(issue_id) for issue_id in completed}
  ready = [
    issue_id
    for issue_id, relation in graph.issues.items()
    if issue_id not in done
    and all(dependency in done for dependency in relation.depends_on)
  ]
  return tuple(_sorted_issue_ids(ready))


def _parse_issue(issue_id: str, raw: dict) -> IssueRelationships:
  expected = {
    "umbrella",
    "shared_umbrellas",
    "depends_on",
    "umbrella_depends_on",
    "parent",
  }
  unknown = set(raw) - expected
  missing = expected - set(raw)
  if unknown:
    raise RelationshipSchemaError(
      f"issue {issue_id}: unknown fields: {sorted(unknown)!r}"
    )
  if missing:
    raise RelationshipSchemaError(
      f"issue {issue_id}: missing fields: {sorted(missing)!r}"
    )

  umbrella = _optional_issue_id(raw["umbrella"], "umbrella")
  shared = _issue_id_list(raw["shared_umbrellas"], "shared_umbrellas")
  dependencies = _issue_id_list(raw["depends_on"], "depends_on")
  umbrella_dependencies = _issue_id_list(
    raw["umbrella_depends_on"],
    "umbrella_depends_on",
  )
  parent = _optional_text(raw["parent"], "parent")

  for kind, values in (
    ("umbrella", (() if umbrella is None else (umbrella,))),
    ("shared umbrella", shared),
    ("direct dependency", dependencies),
    ("umbrella dependency", umbrella_dependencies),
  ):
    if issue_id in values:
      raise RelationshipSchemaError(
        f"issue {issue_id}: self {kind} is not allowed"
      )

  return IssueRelationships(
    umbrella=umbrella,
    shared_umbrellas=shared,
    depends_on=dependencies,
    umbrella_depends_on=umbrella_dependencies,
    parent=parent,
  )


def _validate_direct_dependencies(
  issues: dict[str, IssueRelationships],
) -> None:
  for issue_id, relation in issues.items():
    for dependency in relation.depends_on:
      if dependency not in issues:
        raise RelationshipSchemaError(
          f"issue {issue_id}: unknown direct dependency {dependency}"
        )

  visiting: set[str] = set()
  visited: set[str] = set()

  def visit(issue_id: str) -> None:
    if issue_id in visiting:
      raise RelationshipSchemaError(
        f"direct dependency cycle includes issue {issue_id}"
      )
    if issue_id in visited:
      return
    visiting.add(issue_id)
    for dependency in issues[issue_id].depends_on:
      visit(dependency)
    visiting.remove(issue_id)
    visited.add(issue_id)

  for issue_id in _sorted_issue_ids(issues):
    visit(issue_id)


def _issue_id(value: str | int) -> str:
  if isinstance(value, bool):
    raise RelationshipSchemaError(f"invalid issue id: {value!r}")
  text = str(value)
  if not text.isdigit() or int(text) < 1:
    raise RelationshipSchemaError(f"invalid issue id: {value!r}")
  return str(int(text))


def _optional_issue_id(value, field: str) -> str | None:
  if value is None:
    return None
  try:
    return _issue_id(value)
  except RelationshipSchemaError as error:
    raise RelationshipSchemaError(f"{field}: {error}") from error


def _issue_id_list(value, field: str) -> tuple[str, ...]:
  if not isinstance(value, list):
    raise RelationshipSchemaError(f"{field} must be an array")
  result = tuple(_issue_id(item) for item in value)
  if len(result) != len(set(result)):
    raise RelationshipSchemaError(f"{field} contains duplicates")
  return tuple(_sorted_issue_ids(result))


def _optional_text(value, field: str) -> str | None:
  if value is None:
    return None
  if not isinstance(value, str) or not value.strip():
    raise RelationshipSchemaError(f"{field} must be non-empty text or null")
  return value


def _sorted_issue_ids(values) -> list[str]:
  return sorted(values, key=lambda value: int(value))
