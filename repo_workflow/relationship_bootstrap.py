from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lane_diagnostics import LaneDiagnostics
from .dependency_migration_certification import (
  DependencyMigrationCertificationError,
  require_dependency_migration_certified,
)
from .relationship_store import (
  RelationshipSnapshot,
  RelationshipStore,
  RelationshipStoreError,
)
from .relationships import IssueRelationships, RelationshipGraph
from .state_store import WriterIdentity
from .ticket_dependency_adapter import (
  TicketDependencyError,
  read_ticket_dependencies,
  resolve_dependency_config,
)


@dataclass(frozen=True)
class RelationshipAcquisition:
  issues: tuple[int, ...]
  provider_reads: tuple[int, ...]


def ensure_relationship_graph(
  root: Path,
  roots: tuple[str | int, ...],
  writer: WriterIdentity,
  *,
  refresh: bool = False,
  diagnostics: LaneDiagnostics | None = None,
) -> RelationshipAcquisition:
  """Ensure canonical graph coverage using local state unless refresh/missing."""
  try:
    require_dependency_migration_certified(root)
  except DependencyMigrationCertificationError as error:
    raise TicketDependencyError(str(error)) from error

  store = RelationshipStore(root)
  snapshot = _read_optional(store)
  issues = {} if snapshot is None else dict(snapshot.graph.issues)
  requested = tuple(sorted({str(int(value)) for value in roots}, key=int))
  config = resolve_dependency_config(root)
  pending = list(requested)
  visited: set[str] = set()
  provider_reads: list[int] = []
  changed = snapshot is None

  while pending:
    issue = pending.pop(0)
    if issue in visited:
      continue
    visited.add(issue)

    current = issues.get(issue)
    provider: tuple[str, ...] | None = None
    if refresh or current is None:
      number = int(issue)
      provider_reads.append(number)
      if diagnostics is not None:
        diagnostics.miss("relationships")
        raw = diagnostics.provider(
          "dependencies",
          number,
          lambda: read_ticket_dependencies(root, config, number),
        )
      else:
        raw = read_ticket_dependencies(root, config, number)
      provider = tuple(str(value) for value in raw)
    elif diagnostics is not None:
      diagnostics.hit("relationships")

    if current is None:
      assert provider is not None
      issues[issue] = IssueRelationships(
        umbrella=None,
        shared_umbrellas=(),
        depends_on=provider,
        umbrella_depends_on=(),
        parent=None,
      )
      changed = True
      dependencies = provider
    elif provider is None:
      dependencies = current.depends_on
    elif current.depends_on == provider:
      dependencies = current.depends_on
    elif not current.depends_on and provider:
      issues[issue] = IssueRelationships(
        umbrella=current.umbrella,
        shared_umbrellas=current.shared_umbrellas,
        depends_on=provider,
        umbrella_depends_on=current.umbrella_depends_on,
        parent=current.parent,
      )
      changed = True
      dependencies = provider
    else:
      raise TicketDependencyError(
        "canonical relationship dependencies conflict with native ticket "
        f"dependencies for #{issue}: "
        f"canonical={list(current.depends_on)!r}, provider={list(provider)!r}; "
        "reconcile explicitly before lane selection"
      )

    for dependency in dependencies:
      if dependency not in visited and dependency not in pending:
        pending.append(dependency)

  if changed:
    graph = RelationshipGraph.from_json_value({
      "schema_version": 2,
      "issues": {
        issue: relation.to_json_value()
        for issue, relation in issues.items()
      },
    })

    if snapshot is None:
      store.create(graph, writer)
    else:
      store.replace(snapshot.revision, graph, writer)

  return RelationshipAcquisition(
    issues=tuple(sorted((int(issue) for issue in visited))),
    provider_reads=tuple(provider_reads),
  )


def _read_optional(store: RelationshipStore) -> RelationshipSnapshot | None:
  try:
    return store.read()
  except RelationshipStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise
