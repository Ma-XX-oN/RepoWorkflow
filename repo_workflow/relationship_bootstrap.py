from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lane_decomposition import dependency_component
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
from .repo_info_adapter import issue_info, resolve_info_config
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
  """Ensure canonical ticket coverage using local state unless refresh/missing."""
  try:
    require_dependency_migration_certified(root)
  except DependencyMigrationCertificationError as error:
    raise TicketDependencyError(str(error)) from error

  store = RelationshipStore(root)
  snapshot = _read_optional(store)
  issues = {} if snapshot is None else dict(snapshot.graph.issues)
  requested = tuple(sorted({str(int(value)) for value in roots}, key=int))
  dependency_config = resolve_dependency_config(root)
  info_config = resolve_info_config(root)
  if (
    refresh
    and snapshot is not None
    and all(issue in issues for issue in requested)
  ):
    pending = list(dependency_component(snapshot.graph, requested))
  else:
    pending = list(requested)
  visited: set[str] = set()
  provider_reads: list[int] = []
  fetched_info: dict[int, dict] = {}
  changed = snapshot is None

  while pending:
    issue = pending.pop(0)
    if issue in visited:
      continue
    visited.add(issue)

    current = issues.get(issue)
    provider: IssueRelationships | None = None
    if refresh or current is None:
      number = int(issue)
      provider_reads.append(number)
      if diagnostics is not None:
        diagnostics.miss("relationships")
        diagnostics.miss("metadata")
        dependencies = diagnostics.provider(
          "dependencies",
          number,
          lambda: read_ticket_dependencies(
            root,
            dependency_config,
            number,
          ),
        )
        info = diagnostics.provider(
          "metadata",
          number,
          lambda: issue_info(root, info_config, number),
        )
      else:
        dependencies = read_ticket_dependencies(
          root,
          dependency_config,
          number,
        )
        info = issue_info(root, info_config, number)
      fetched_info[number] = info
      provider = IssueRelationships(
        title=info["title"],
        depends_on=tuple(str(value) for value in dependencies),
      )
    elif diagnostics is not None:
      diagnostics.hit("relationships")

    if current is None:
      assert provider is not None
      issues[issue] = provider
      changed = True
      dependencies = provider.depends_on
    elif provider is None:
      dependencies = current.depends_on
    else:
      if current.depends_on == provider.depends_on:
        replacement = provider
      elif not current.depends_on and provider.depends_on:
        replacement = provider
      else:
        raise TicketDependencyError(
          "canonical dependencies conflict with native ticket dependencies "
          f"for #{issue}: canonical={list(current.depends_on)!r}, "
          f"provider={list(provider.depends_on)!r}; reconcile explicitly "
          "before lane selection"
        )
      if replacement != current:
        issues[issue] = replacement
        changed = True
      dependencies = replacement.depends_on

    for dependency in dependencies:
      if dependency not in visited and dependency not in pending:
        pending.append(dependency)

  if changed:
    graph = RelationshipGraph.from_json_value({
      "schema_version": 3,
      "issues": {
        issue: relation.to_json_value()
        for issue, relation in issues.items()
      },
    })

    if snapshot is None:
      store.create(graph, writer)
    else:
      store.replace(snapshot.revision, graph, writer)
  else:
    assert snapshot is not None
    graph = snapshot.graph

  component = dependency_component(graph, requested)

  if fetched_info:
    from .issue_metadata import cache_issue_display_metadata
    cache_issue_display_metadata(root, fetched_info, writer)

  return RelationshipAcquisition(
    issues=tuple(int(issue) for issue in component),
    provider_reads=tuple(provider_reads),
  )


def _read_optional(store: RelationshipStore) -> RelationshipSnapshot | None:
  try:
    return store.read()
  except RelationshipStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise
