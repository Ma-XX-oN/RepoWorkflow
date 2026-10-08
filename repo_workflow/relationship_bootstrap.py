from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lane_decomposition import dependency_component, dependency_states
from .lane_traversal import (
  FollowPolicy,
  ShowChildrenPolicy,
  TraversalState,
  group_kind,
)
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
  read_ticket_relationships,
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
  follow: FollowPolicy | None = None,
  show_children: ShowChildrenPolicy | None = None,
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
  requested_set = set(requested)
  policy = FollowPolicy() if follow is None else follow
  context = ShowChildrenPolicy() if show_children is None else show_children
  dependency_config = resolve_dependency_config(root)
  info_config = resolve_info_config(root)
  if (
    refresh
    and snapshot is not None
    and all(issue in issues for issue in requested)
  ):
    pending = [
      (state, True)
      for state in dependency_states(
        snapshot.graph,
        requested,
        follow=policy,
      )
    ]
  else:
    pending = [
      (TraversalState(issue, policy.remaining()), True)
      for issue in requested
    ]
  visited: set[TraversalState] = set()
  traversed_issues: set[str] = set()
  context_issues: set[str] = set()
  provider_reads: list[int] = []
  fetched_info: dict[int, dict] = {}
  provider_cache: dict[
    str,
    tuple[IssueRelationships, tuple[str, ...], dict],
  ] = {}
  changed = snapshot is None

  while pending:
    state, traverse = pending.pop(0)
    issue = state.issue
    if traverse:
      if state in visited:
        continue
      visited.add(state)
      traversed_issues.add(issue)
    else:
      if issue in context_issues or issue in traversed_issues:
        continue
      context_issues.add(issue)

    current = issues.get(issue)
    provider: IssueRelationships | None = None
    if refresh or current is None:
      cached_provider = provider_cache.get(issue)
      if cached_provider is not None:
        provider, provider_dependants, info = cached_provider
      else:
        number = int(issue)
        provider_reads.append(number)
        if diagnostics is not None:
          diagnostics.miss("relationships")
          diagnostics.miss("metadata")
          relationships = diagnostics.provider(
            "dependencies",
            number,
            lambda: read_ticket_relationships(
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
          relationships = read_ticket_relationships(
            root,
            dependency_config,
            number,
          )
          info = issue_info(root, info_config, number)
        fetched_info[number] = info
        provider = IssueRelationships(
          title=info["title"],
          depends_on=tuple(str(value) for value in relationships.dependencies),
        )
        provider_dependants = tuple(
          str(value) for value in relationships.dependants
        )
        provider_cache[issue] = (provider, provider_dependants, info)
    else:
      provider_dependants = ()
      if diagnostics is not None:
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

    if not traverse:
      for dependency in dependencies:
        if dependency not in traversed_issues and dependency not in context_issues:
          pending.append((
            TraversalState(dependency, state.remaining),
            False,
          ))
      continue

    remaining = state.remaining
    relation = issues[issue]
    kind = group_kind(relation.title)
    related = (*dependencies, *provider_dependants)
    if not policy.enables_traversal():
      for dependency in dependencies:
        pending.append((
          TraversalState(dependency, remaining),
          False,
        ))
      continue
    if issue not in requested_set:
      crossed = policy.cross(kind, remaining)
      if crossed is None:
        if context.matches(kind):
          for related_issue in related:
            pending.append((
              TraversalState(related_issue, remaining),
              False,
            ))
        continue
      remaining = crossed

    for related_issue in related:
      next_state = TraversalState(related_issue, remaining)
      if next_state not in visited:
        pending.append((next_state, True))

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

  component = dependency_component(
    graph,
    requested,
    follow=policy,
    show_children=context,
  )

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
