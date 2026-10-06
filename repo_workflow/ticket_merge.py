from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .relationship_store import _parse_csv, _render_csv
from .relationships import IssueRelationships, RelationshipGraph
from .repo_info_adapter import issue_info, resolve_info_config


class TicketMergeError(RuntimeError):
  """Raised when synchronized ticket state cannot be merged safely."""


@dataclass(frozen=True)
class MergeInputs:
  base: RelationshipGraph
  ours: RelationshipGraph
  theirs: RelationshipGraph


def merge_ticket_csv(
  root: Path,
  base_text: str,
  ours_text: str,
  theirs_text: str,
) -> str:
  inputs = MergeInputs(
    _parse_csv(base_text),
    _parse_csv(ours_text),
    _parse_csv(theirs_text),
  )
  issues: dict[str, IssueRelationships] = {}
  for issue in sorted(
    set(inputs.base.issues)
    | set(inputs.ours.issues)
    | set(inputs.theirs.issues),
    key=int,
  ):
    base = inputs.base.issues.get(issue)
    ours = inputs.ours.issues.get(issue)
    theirs = inputs.theirs.issues.get(issue)
    merged = _merge_record(
      root,
      int(issue),
      base,
      ours,
      theirs,
    )
    if merged is not None:
      issues[issue] = merged

  return _render_csv(RelationshipGraph(issues))


def _merge_record(
  root: Path,
  issue: int,
  base: IssueRelationships | None,
  ours: IssueRelationships | None,
  theirs: IssueRelationships | None,
) -> IssueRelationships | None:
  if ours == theirs:
    return ours
  if ours == base:
    return theirs
  if theirs == base:
    return ours

  if ours is None or theirs is None:
    raise TicketMergeError(
      f"ticket #{issue} was deleted on one side and modified on the other"
    )

  dependencies = _merge_dependencies(
    issue,
    None if base is None else base.depends_on,
    ours.depends_on,
    theirs.depends_on,
  )

  if ours.title == theirs.title:
    title = ours.title
  else:
    try:
      provider = resolve_info_config(root)
      title = issue_info(root, provider, issue)["title"]
    except Exception as error:
      raise TicketMergeError(
        f"cannot resolve authoritative title for ticket #{issue}: {error}"
      ) from error

  return IssueRelationships(title=title, depends_on=dependencies)


def _merge_dependencies(
  issue: int,
  base: tuple[str, ...] | None,
  ours: tuple[str, ...],
  theirs: tuple[str, ...],
) -> tuple[str, ...]:
  if ours == theirs:
    return ours
  if base is not None and ours == base:
    return theirs
  if base is not None and theirs == base:
    return ours
  raise TicketMergeError(
    f"ticket #{issue} has divergent dependency changes: "
    f"ours={list(ours)!r}, theirs={list(theirs)!r}"
  )


def merge_files(
  root: Path,
  base_path: Path,
  ours_path: Path,
  theirs_path: Path,
) -> None:
  merged = merge_ticket_csv(
    root,
    base_path.read_text(encoding="utf-8"),
    ours_path.read_text(encoding="utf-8"),
    theirs_path.read_text(encoding="utf-8"),
  )
  ours_path.write_text(merged, encoding="utf-8", newline="")
