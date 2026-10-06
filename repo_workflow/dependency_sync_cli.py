from __future__ import annotations

import json
from pathlib import Path

from .config import load_config
from .dependency_comparison import (
  DependencyComparisonStatus,
  compare_dependencies,
)
from .dependency_sync import DependencySyncConflict, read_ticket_sync_state
from .issue_metadata import refresh_issue_metadata
from .relationship_store import RelationshipStore
from .relationships import IssueRelationships, RelationshipGraph
from .repo_info_adapter import resolve_info_config
from .runtime_identity import runtime_writer_identity
from .ticket_dependency_adapter import (
  read_ticket_dependencies,
  replace_ticket_dependencies,
  resolve_dependency_config,
)


def dependency_sync_command(root: Path, words: tuple[str, ...]) -> int:
  issues, direction, option = _parse(words)
  config = load_config(root)
  store = RelationshipStore(root)
  snapshot = store.read()

  observations = {}
  for issue in issues:
    relation = snapshot.graph.issue(issue)
    title, dependencies = read_ticket_sync_state(
      root,
      config,
      issue,
    )
    observations[issue] = (relation, title, dependencies)

  if option == "--compare":
    for issue in issues:
      relation, title, ticket = observations[issue]
      local = tuple(int(value) for value in relation.depends_on)
      comparison = (
        compare_dependencies(local, ticket)
        if direction == "to-tickets"
        else compare_dependencies(ticket, local)
      )
      print(json.dumps({
        "issue": issue,
        "direction": direction,
        "title": {
          "local": relation.title,
          "ticket": title,
          "match": relation.title == title,
        },
        "dependencies": {
          "status": comparison.status.value,
          "source": list(comparison.source),
          "destination": list(comparison.destination),
          "additions": list(comparison.additions),
          "removals": list(comparison.removals),
        },
      }, separators=(",", ":")))
    return 0

  if direction == "from-tickets":
    return _from_tickets(
      root,
      config,
      store,
      snapshot,
      issues,
      observations,
      option,
    )
  return _to_tickets(
    root,
    config,
    issues,
    observations,
    replace=option == "--replace",
  )


def _parse(
  words: tuple[str, ...],
) -> tuple[tuple[int, ...], str, str | None]:
  try:
    marker = words.index("dependency")
  except ValueError as error:
    raise ValueError("dependency synchronization command is missing dependency") from error
  if marker < 1 or len(words) not in {marker + 2, marker + 3}:
    raise ValueError("invalid dependency synchronization command")

  issues: list[int] = []
  seen: set[int] = set()
  for value in words[:marker]:
    if not value.isdecimal() or int(value) <= 0:
      raise ValueError(f"invalid issue number: {value}")
    number = int(value)
    if number in seen:
      raise ValueError(f"duplicate issue number: {number}")
    seen.add(number)
    issues.append(number)

  direction = words[marker + 1]
  if direction not in {"to-tickets", "from-tickets"}:
    raise ValueError("invalid dependency synchronization direction")
  option = None if len(words) == marker + 2 else words[-1]
  allowed = {None, "--compare", "--replace"}
  if direction == "from-tickets":
    allowed |= {"--replace-title", "--replace-dependencies"}
  if option not in allowed:
    raise ValueError(
      f"invalid dependency synchronization option for {direction}: {option}"
    )
  return tuple(issues), direction, option


def _from_tickets(
  root: Path,
  config: dict,
  store: RelationshipStore,
  snapshot,
  issues: tuple[int, ...],
  observations: dict,
  option: str | None,
) -> int:
  replace_all = option == "--replace"
  replace_title_only = option == "--replace-title"
  replace_deps = replace_all or option == "--replace-dependencies"

  replacements = dict(snapshot.graph.issues)
  results = []
  for issue in issues:
    relation, title, ticket = observations[issue]
    local = tuple(int(value) for value in relation.depends_on)
    comparison = compare_dependencies(ticket, local)
    dependency_conflict = (
      comparison.status != DependencyComparisonStatus.MATCH
      and bool(comparison.destination)
    )
    if dependency_conflict and not replace_deps and not replace_title_only:
      raise DependencySyncConflict(
        f"RWF dependencies conflict for issue #{issue}: "
        f"tickets={list(ticket)} RWF={list(local)}"
      )

    if dependency_conflict and replace_title_only:
      dependencies = relation.depends_on
      status = "PARTIAL"
    elif (
      comparison.status == DependencyComparisonStatus.MATCH
      or (not comparison.destination and not ticket)
    ):
      dependencies = relation.depends_on
      status = "MATCH" if title == relation.title else "SYNCHRONIZED"
    else:
      dependencies = tuple(str(value) for value in ticket)
      status = "SYNCHRONIZED"

    replacement = IssueRelationships(
      title=title,
      depends_on=dependencies,
    )
    replacements[str(issue)] = replacement
    if replacement != relation and status == "MATCH":
      status = "SYNCHRONIZED"
    results.append((issue, status, replacement, comparison))

  graph = RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in replacements.items()
    },
  })
  if graph != snapshot.graph:
    store.replace(snapshot.revision, graph, runtime_writer_identity())

  for issue, status, replacement, comparison in results:
    print(json.dumps({
      "issue": issue,
      "direction": "from-tickets",
      "status": status,
      "title": replacement.title,
      "dependencies": [int(x) for x in replacement.depends_on],
      "dependency_status": comparison.status.value,
    }, separators=(",", ":")))
  return 0


def _to_tickets(
  root: Path,
  config: dict,
  issues: tuple[int, ...],
  observations: dict,
  *,
  replace: bool,
) -> int:
  plans = []
  for issue in issues:
    relation, title, ticket = observations[issue]
    if title != relation.title:
      raise DependencySyncConflict(
        f"ticket title conflict for issue #{issue}: "
        f"RWF={relation.title!r} tickets={title!r}"
      )
    local = tuple(int(value) for value in relation.depends_on)
    comparison = compare_dependencies(local, ticket)
    if (
      comparison.status != DependencyComparisonStatus.MATCH
      and comparison.destination
      and not replace
    ):
      raise DependencySyncConflict(
        f"ticket dependencies conflict for issue #{issue}: "
        f"RWF={list(local)} tickets={list(ticket)}"
      )
    plans.append((issue, relation, ticket, comparison))

  dependency_config = resolve_dependency_config(root, config)
  changed: list[tuple[int, tuple[int, ...]]] = []
  try:
    for issue, relation, ticket, comparison in plans:
      local = tuple(int(value) for value in relation.depends_on)
      if comparison.status == DependencyComparisonStatus.MATCH:
        continue
      replace_ticket_dependencies(
        root,
        dependency_config,
        issue,
        local,
      )
      changed.append((issue, ticket))
      title, readback = read_ticket_sync_state(root, config, issue)
      if title != relation.title or readback != local:
        raise DependencySyncConflict(
          f"ticket readback changed while synchronizing issue #{issue}"
        )
  except Exception as error:
    rollback_failures = []
    for issue, original in reversed(changed):
      try:
        replace_ticket_dependencies(
          root,
          dependency_config,
          issue,
          original,
        )
      except Exception as rollback:
        rollback_failures.append(f"#{issue}: {rollback}")
    if rollback_failures:
      raise DependencySyncConflict(
        f"{error}; rollback failed for " + "; ".join(rollback_failures)
      ) from error
    raise

  refresh_issue_metadata(
    root,
    resolve_info_config(root, config),
    runtime_writer_identity(),
    issues,
  )
  for issue, relation, _ticket, comparison in plans:
    print(json.dumps({
      "issue": issue,
      "direction": "to-tickets",
      "status": (
        "MATCH"
        if comparison.status == DependencyComparisonStatus.MATCH
        else "SYNCHRONIZED"
      ),
      "title": relation.title,
      "dependencies": [int(x) for x in relation.depends_on],
    }, separators=(",", ":")))
  return 0
