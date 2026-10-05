from __future__ import annotations

from pathlib import Path

from .issue_metadata import IssueMetadataStore
from .lane_selection import LaneSelectionStore


class LaneListError(RuntimeError):
  pass


def render_lane_list(
  root: Path,
  *,
  lane: str | None = None,
  links: bool = False,
) -> tuple[str, ...]:
  selection = LaneSelectionStore(root).read().value
  if selection is None:
    raise LaneListError("lane selection is missing")

  requested = None if lane is None else lane.upper()
  lanes = sorted(set(selection.assignment.values()))
  if requested is not None:
    if requested not in lanes:
      raise LaneListError(f"unknown selected lane: {requested}")
    lanes = [requested]

  metadata = IssueMetadataStore(root)
  lines: list[str] = []
  for index, lane_name in enumerate(lanes):
    if index:
      lines.append("")
    lines.append(f"Lane {lane_name}")
    issues = sorted(
      (
        issue
        for issue in selection.closure
        if selection.assignment[issue] == lane_name
      ),
      key=int,
    )
    for issue in issues:
      value = metadata.display_issue(int(issue))
      line = f"#{issue}  {value.title}"
      if links:
        line += f"  {value.link}"
      lines.append(line)
  return tuple(lines)
