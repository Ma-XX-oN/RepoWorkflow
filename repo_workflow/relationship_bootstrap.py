from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lane_decomposition import dependency_component
from .lane_traversal import (
  FollowPolicy,
  ShowChildrenPolicy,
  TraversalState,
  dependant_boundary_kind,
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
  """Ensure canonical ticket coverage for terminal-root lane discovery."""
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

  if (
    not refresh
    and snapshot is not None
    and all(issue in issues for issue in requested)
  ):
    component = dependency_component(
      snapshot.graph,
      requested,
      follow=policy,
      show_children=context,
    )
    return RelationshipAcquisition(
      issues=tuple(int(issue) for issue in component),
      provider_reads=(),
    )

  dependency_config = resolve_dependency_config(root)
  info_config = resolve_info_config(root)
  provider_reads: list[int] = []
  fetched_info: dict[int, dict] = {}
  provider_cache: dict[
    str,
    tuple[IssueRelationships, tuple[str, ...], dict],
  ] = {}
  changed = snapshot is None

  def load(issue: str) -> tuple[IssueRelationships, tuple[str, ...]]:
    nonlocal changed
    cached = provider_cache.get(issue)
    if cached is not None:
      relation, dependants, _ = cached
      return relation, dependants

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
      str(value)
      for value in relationships.dependants
    )
    provider_cache[issue] = (provider, provider_dependants, info)

    current = issues.get(issue)
    if current is None:
      issues[issue] = provider
      changed = True
    elif current.depends_on == provider.depends_on:
      if current != provider:
        issues[issue] = provider
        changed = True
    elif not current.depends_on and provider.depends_on:
      issues[issue] = provider
      changed = True
    else:
      raise TicketDependencyError(
        "canonical dependencies conflict with native ticket dependencies "
        f"for #{issue}: canonical={list(current.depends_on)!r}, "
        f"provider={list(provider.depends_on)!r}; reconcile explicitly "
        "before lane selection"
      )

    return issues[issue], provider_dependants

  support_seen: set[str] = set()

  def ensure_support(issue: str) -> None:
    pending = [issue]
    while pending:
      current_issue = pending.pop(0)
      if current_issue in support_seen:
        continue
      support_seen.add(current_issue)
      relation, _ = load(current_issue)
      for dependency in relation.depends_on:
        if dependency not in support_seen:
          pending.append(dependency)

  dependency_visited: set[TraversalState] = set()
  stopped_dependency_groups: set[TraversalState] = set()
  terminals: set[TraversalState] = set()
  pending_left = [
    TraversalState(issue, policy.remaining())
    for issue in requested
  ]

  while pending_left:
    state = pending_left.pop(0)
    if state in dependency_visited:
      continue
    dependency_visited.add(state)

    relation, _ = load(state.issue)
    remaining = state.remaining
    kind = group_kind(relation.title)
    if state.issue not in requested_set:
      crossed = policy.cross(kind, remaining)
      if crossed is None:
        stopped_dependency_groups.add(state)
        terminals.add(state)
        if context.matches(kind):
          for dependency in relation.depends_on:
            ensure_support(dependency)
        continue
      remaining = crossed

    if not relation.depends_on:
      terminals.add(TraversalState(state.issue, remaining))
      continue

    for dependency in relation.depends_on:
      next_state = TraversalState(dependency, remaining)
      if next_state not in dependency_visited and next_state not in pending_left:
        pending_left.append(next_state)

  pending_right: list[tuple[TraversalState, bool]] = []
  for terminal in sorted(
    terminals,
    key=lambda state: (int(state.issue), state.remaining),
  ):
    if terminal in stopped_dependency_groups:
      continue
    relation, _ = load(terminal.issue)
    if (
      terminal.issue not in requested_set
      and dependant_boundary_kind(relation.title) is not None
    ):
      continue
    pending_right.append((terminal, False))

  dependant_visited: set[TraversalState] = set()
  while pending_right:
    state, cross_current = pending_right.pop(0)
    if state in dependant_visited:
      continue
    dependant_visited.add(state)

    relation, provider_dependants = load(state.issue)
    remaining = state.remaining
    if cross_current and state.issue not in requested_set:
      kind = group_kind(relation.title)
      crossed = policy.cross(kind, remaining)
      if crossed is None:
        if context.matches(kind):
          for dependant in provider_dependants:
            ensure_support(dependant)
        continue
      remaining = crossed

    for dependant in provider_dependants:
      ensure_support(dependant)
      next_state = TraversalState(dependant, remaining)
      if (
        next_state not in dependant_visited
        and all(item[0] != next_state for item in pending_right)
      ):
        pending_right.append((next_state, True))

  graph = RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in issues.items()
    },
  })

  if changed:
    if snapshot is None:
      store.create(graph, writer)
    else:
      store.replace(snapshot.revision, graph, writer)

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
