from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shlex
import subprocess
import sys

from .relationship_store import _parse_ticket_csv, _render_csv, TicketState
from .lifecycle_store import LifecycleStore
from .relationships import IssueRelationships, RelationshipGraph
from .repo_info_adapter import issue_info, resolve_info_config


class TicketMergeError(RuntimeError):
  """Raised when synchronized ticket state cannot be merged safely."""


def configure_ticket_merge_driver(root: Path, engine_root: Path) -> None:
  """Install the repository-local Git merge driver used by tickets.csv."""
  repository = Path(root).resolve()
  script = Path(engine_root).resolve() / "scripts" / "merge-ticket-state.py"
  if not script.is_file():
    raise TicketMergeError(f"ticket merge driver is missing: {script}")
  driver = " ".join((
    shlex.quote(os.fspath(Path(sys.executable).resolve())),
    shlex.quote(os.fspath(script)),
    "%O",
    "%A",
    "%B",
  ))
  commands = (
    ("merge.rwf-tickets.name", "RepoWorkflow synchronized ticket merge"),
    ("merge.rwf-tickets.driver", driver),
  )
  for key, value in commands:
    result = subprocess.run(
      ["git", "-C", os.fspath(repository), "config", "--local", key, value],
      capture_output=True,
      text=True,
      check=False,
    )
    if result.returncode:
      detail = (result.stderr or result.stdout).strip()
      raise TicketMergeError(
        f"cannot configure ticket merge driver {key}"
        + (f": {detail}" if detail else "")
      )


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
  base_graph, base_states = _parse_ticket_csv(base_text)
  ours_graph, ours_states = _parse_ticket_csv(ours_text)
  theirs_graph, theirs_states = _parse_ticket_csv(theirs_text)
  inputs = MergeInputs(base_graph, ours_graph, theirs_graph)
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

  all_states = None
  if any(x is not None for x in (base_states, ours_states, theirs_states)):
    all_states = {}
    lifecycle = LifecycleStore(root)
    for issue in sorted(issues, key=int):
      def lookup(values):
        return None if values is None else values.get(issue)
      value = _merge_state(
        issue,
        lookup(base_states),
        lookup(ours_states),
        lookup(theirs_states),
      )
      if value is None:
        current = lifecycle.read(issue)
        value = TicketState(current.lifecycle.state, current.revision)
      all_states[issue] = value
  return _render_csv(RelationshipGraph(issues), all_states)


def _merge_state(
  issue: str,
  base: TicketState | None,
  ours: TicketState | None,
  theirs: TicketState | None,
) -> TicketState | None:
  if ours == theirs:
    return ours
  if ours == base:
    return theirs
  if theirs == base:
    return ours
  if ours is None:
    return theirs
  if theirs is None:
    return ours
  raise TicketMergeError(
    f'ticket #{issue} has divergent lifecycle projections'
  )


def _merge_record(
  root: Path,
  issue: int,
  base: IssueRelationships | None,
  ours: IssueRelationships | None,
  theirs: IssueRelationships | None,
) -> IssueRelationships | None:
  if ours is None and theirs is None:
    return None
  if ours is None or theirs is None:
    if ours == base:
      return theirs
    if theirs == base:
      return ours
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
