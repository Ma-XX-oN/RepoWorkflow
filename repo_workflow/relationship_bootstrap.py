from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dependency_migration_certification import (
  DependencyMigrationCertificationError,
  require_dependency_migration_certified,
)
from .lane_diagnostics import LaneDiagnostics
from .lane_projection import (
  ProjectionRule,
  normalize_rules,
  project_rules,
)
from .lane_relationship_coverage import (
  RelationshipCoverage,
  RelationshipCoverageStore,
  rule_is_covered,
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
  **obsolete,
) -> RelationshipAcquisition:
  """Compatibility wrapper for default-both explicit seed projection."""
  del obsolete
  rules = tuple(
    ProjectionRule(str(int(value)), "both")
    for value in roots
  )
  return ensure_relationship_rules(
    root,
    rules,
    (),
    writer,
    refresh=refresh,
    diagnostics=diagnostics,
  )


def ensure_relationship_rules(
  root: Path,
  includes: tuple[ProjectionRule, ...],
  excludes: tuple[ProjectionRule, ...],
  writer: WriterIdentity,
  *,
  refresh: bool = False,
  diagnostics: LaneDiagnostics | None = None,
) -> RelationshipAcquisition:
  """Ensure synchronized relationship coverage for explicit projection rules."""
  try:
    require_dependency_migration_certified(root)
  except DependencyMigrationCertificationError as error:
    raise TicketDependencyError(str(error)) from error

  include_rules = normalize_rules(includes)
  exclude_rules = normalize_rules(excludes)
  all_rules = normalize_rules((*include_rules, *exclude_rules))
  if not include_rules:
    raise TicketDependencyError("lane selection requires an include rule")

  store = RelationshipStore(root)
  snapshot = _read_optional(store)
  issues = {} if snapshot is None else dict(snapshot.graph.issues)
  requested = {rule.seed for rule in all_rules}
  initial_issue_ids = tuple(sorted(issues, key=int))
  coverage_store = RelationshipCoverageStore(root)
  coverage, coverage_revision = coverage_store.read()
  partial = (
    snapshot is None
    or bool(requested - set(issues))
    or (coverage is not None and coverage.partial)
  )

  locally_covered = (
    coverage is None
    or all(rule_is_covered(coverage, rule) for rule in all_rules)
  )
  if (
    not refresh
    and snapshot is not None
    and requested <= set(issues)
    and locally_covered
  ):
    projected = project_rules(
      snapshot.graph,
      include_rules,
      exclude_rules,
    )
    return RelationshipAcquisition(
      issues=tuple(int(issue) for issue in projected),
      provider_reads=(),
    )

  dependency_config = resolve_dependency_config(root)
  info_config = resolve_info_config(root)
  provider_reads: list[int] = []
  fetched_info: dict[int, dict] = {}
  provider_cache: dict[
    str,
    tuple[IssueRelationships, tuple[str, ...]],
  ] = {}
  changed = snapshot is None

  def local_dependents(issue: str) -> tuple[str, ...]:
    return tuple(sorted(
      (
        candidate
        for candidate, relation in issues.items()
        if issue in relation.depends_on
      ),
      key=int,
    ))

  def load(
    issue: str,
    *,
    force_provider: bool,
  ) -> tuple[IssueRelationships, tuple[str, ...]]:
    nonlocal changed

    cached = provider_cache.get(issue)
    if cached is not None:
      return cached

    if not force_provider and not refresh and issue in issues:
      if diagnostics is not None:
        diagnostics.hit("relationships")
      return issues[issue], local_dependents(issue)

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
    provider_dependents = tuple(
      str(value) for value in relationships.dependants
    )
    provider_cache[issue] = (provider, provider_dependents)

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

    return issues[issue], provider_dependents

  support_seen: set[tuple[str, bool]] = set()

  def ensure_support(issue: str, *, force_provider: bool) -> None:
    pending = [issue]
    while pending:
      current_issue = pending.pop()
      key = (current_issue, force_provider)
      if key in support_seen:
        continue
      support_seen.add(key)
      relation, _ = load(
        current_issue,
        force_provider=force_provider,
      )
      pending.extend(
        dependency
        for dependency in relation.depends_on
        if dependency not in support_seen
      )

  def walk_dependencies(seed: str, *, force_provider: bool) -> None:
    pending = [seed]
    seen: set[str] = set()
    while pending:
      issue = pending.pop()
      if issue in seen:
        continue
      seen.add(issue)
      relation, _ = load(issue, force_provider=force_provider)
      pending.extend(
        dependency
        for dependency in relation.depends_on
        if dependency not in seen
      )

  def walk_dependents(seed: str, *, force_provider: bool) -> None:
    pending = [seed]
    seen: set[str] = set()
    while pending:
      issue = pending.pop()
      if issue in seen:
        continue
      seen.add(issue)
      _, dependents = load(issue, force_provider=force_provider)
      for dependant in dependents:
        ensure_support(dependant, force_provider=force_provider)
        if dependant not in seen:
          pending.append(dependant)

  for rule in all_rules:
    force_provider = refresh or (
      partial
      and (
        coverage is None
        or not rule_is_covered(coverage, rule)
      )
    )
    if rule.mode == "single":
      ensure_support(rule.seed, force_provider=force_provider)
    elif rule.mode == "dependencies":
      walk_dependencies(rule.seed, force_provider=force_provider)
    elif rule.mode == "dependents":
      ensure_support(rule.seed, force_provider=force_provider)
      walk_dependents(rule.seed, force_provider=force_provider)
    else:
      walk_dependencies(rule.seed, force_provider=force_provider)
      walk_dependents(rule.seed, force_provider=force_provider)

  graph = RelationshipGraph.from_json_value({
    "schema_version": 3,
    "issues": {
      issue: relation.to_json_value()
      for issue, relation in issues.items()
    },
  })

  next_coverage = None
  if partial:
    prior_rules = () if coverage is None else coverage.rules
    baseline = (
      initial_issue_ids
      if coverage is None and snapshot is not None
      else (() if coverage is None else coverage.baseline_seeds)
    )
    next_coverage = RelationshipCoverage(
      partial=True,
      baseline_seeds=baseline,
      rules=normalize_rules((*prior_rules, *all_rules)),
    )

  # Establish the first partial-coverage marker before mutating tickets.csv so
  # a crash cannot leave a partially acquired graph looking complete.
  if coverage is None and next_coverage is not None:
    coverage_store.write(
      next_coverage,
      writer,
      expected_revision=None,
    )
    coverage_revision = 0

  if changed:
    if snapshot is None:
      store.create(graph, writer)
    else:
      store.replace(snapshot.revision, graph, writer)

  if next_coverage is not None and coverage is not None:
    coverage_store.write(
      next_coverage,
      writer,
      expected_revision=coverage_revision,
    )

  projected = project_rules(graph, include_rules, exclude_rules)

  if fetched_info:
    from .issue_metadata import cache_issue_display_metadata
    cache_issue_display_metadata(root, fetched_info, writer)

  return RelationshipAcquisition(
    issues=tuple(int(issue) for issue in projected),
    provider_reads=tuple(provider_reads),
  )


def _read_optional(store: RelationshipStore) -> RelationshipSnapshot | None:
  try:
    return store.read()
  except RelationshipStoreError as error:
    if "record is missing:" in str(error):
      return None
    raise
