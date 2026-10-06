from __future__ import annotations

from dataclasses import dataclass


SCHEMA_VERSION = 3


class RelationshipSchemaError(ValueError):
  """Raised when synchronized ticket relationships violate their contract."""


@dataclass(frozen=True)
class IssueRelationships:
  title: str
  depends_on: tuple[str, ...]

  def __post_init__(self) -> None:
    if not isinstance(self.title, str) or not self.title:
      raise RelationshipSchemaError("issue title must be non-empty text")
    normalized = _issue_id_list(list(self.depends_on), "depends_on")
    if normalized != self.depends_on:
      object.__setattr__(self, "depends_on", normalized)

  def to_json_value(self) -> dict:
    return {
      "title": self.title,
      "depends_on": list(self.depends_on),
    }


@dataclass(frozen=True)
class RelationshipGraph:
  issues: dict[str, IssueRelationships]
  schema_version: int = SCHEMA_VERSION

  @classmethod
  def from_json_value(cls, value: dict) -> "RelationshipGraph":
    if not isinstance(value, dict):
      raise RelationshipSchemaError("relationship graph must be an object")
    if value.get("schema_version") != SCHEMA_VERSION:
      raise RelationshipSchemaError(
        f"unsupported relationship schema version: {value.get('schema_version')!r}"
      )
    raw_issues = value.get("issues")
    if not isinstance(raw_issues, dict):
      raise RelationshipSchemaError("issues must be an object")

    issues: dict[str, IssueRelationships] = {}
    for raw_issue_id, raw in raw_issues.items():
      issue_id = _issue_id(raw_issue_id)
      if not isinstance(raw, dict) or set(raw) != {"title", "depends_on"}:
        raise RelationshipSchemaError(
          f"issue {issue_id}: expected title and depends_on only"
        )
      title = raw["title"]
      if not isinstance(title, str) or not title:
        raise RelationshipSchemaError(
          f"issue {issue_id}: title must be non-empty text"
        )
      issues[issue_id] = IssueRelationships(
        title=title,
        depends_on=_issue_id_list(raw["depends_on"], "depends_on"),
      )

    _validate_direct_dependencies(issues)
    return cls(issues=issues)

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


def project_legacy_graph(value: dict, titles: dict[str, str]) -> RelationshipGraph:
  """Project legacy relationship state onto title + direct dependencies only."""
  if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
    raise RelationshipSchemaError(
      "legacy relationship graph must use schema version 1 or 2"
    )
  raw_issues = value.get("issues")
  if not isinstance(raw_issues, dict):
    raise RelationshipSchemaError("issues must be an object")

  issues: dict[str, IssueRelationships] = {}
  for raw_issue_id, raw in raw_issues.items():
    issue_id = _issue_id(raw_issue_id)
    if not isinstance(raw, dict) or "depends_on" not in raw:
      raise RelationshipSchemaError(
        f"legacy issue {issue_id}: direct dependencies are missing"
      )
    title = titles.get(issue_id)
    if not isinstance(title, str) or not title:
      raise RelationshipSchemaError(
        f"legacy issue {issue_id}: synchronized title is missing"
      )
    issues[issue_id] = IssueRelationships(
      title=title,
      depends_on=_issue_id_list(raw["depends_on"], "depends_on"),
    )

  _validate_direct_dependencies(issues)
  return RelationshipGraph(issues)


def ready_issues(
  graph: RelationshipGraph,
  completed: set[str | int],
) -> tuple[str, ...]:
  done = {_issue_id(issue_id) for issue_id in completed}
  ready = [
    issue_id
    for issue_id, relation in graph.issues.items()
    if issue_id not in done
    and all(dependency in done for dependency in relation.depends_on)
  ]
  return tuple(_sorted_issue_ids(ready))


def _validate_direct_dependencies(
  issues: dict[str, IssueRelationships],
) -> None:
  for issue_id, relation in issues.items():
    if issue_id in relation.depends_on:
      raise RelationshipSchemaError(
        f"issue {issue_id}: self direct dependency is not allowed"
      )
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


def _issue_id_list(value, field: str) -> tuple[str, ...]:
  if not isinstance(value, list):
    raise RelationshipSchemaError(f"{field} must be an array")
  result = tuple(_issue_id(item) for item in value)
  if len(result) != len(set(result)):
    raise RelationshipSchemaError(f"{field} contains duplicates")
  return tuple(_sorted_issue_ids(result))


def _sorted_issue_ids(values) -> list[str]:
  return sorted(values, key=lambda value: int(value))
