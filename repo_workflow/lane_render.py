from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .issue_metadata import IssueMetadataStore
from .lane_selection import LaneSelectionStore
from .repo_info_adapter import issue_info, resolve_info_config
from .state_store import StateStoreError, WriterIdentity, clone_local_store


SETTINGS_KEY = "settings/display"
VALID_COLORS = {"auto", "always", "never"}


class LaneRenderError(RuntimeError):
  pass


def color_setting(root: Path) -> str:
  try:
    value = clone_local_store(root).read(SETTINGS_KEY)["value"]
  except StateStoreError as error:
    if "record is missing:" in str(error):
      return "auto"
    raise LaneRenderError(str(error)) from error
  color = value.get("color") if isinstance(value, dict) else None
  if color not in VALID_COLORS:
    raise LaneRenderError("invalid persistent color setting")
  return color


def set_color_setting(root: Path, color: str, writer: WriterIdentity) -> str:
  if color not in VALID_COLORS:
    raise LaneRenderError("color must be auto, always, or never")
  store = clone_local_store(root)
  value = {"color": color}
  try:
    current = store.read(SETTINGS_KEY)
  except StateStoreError as error:
    if "record is missing:" not in str(error):
      raise LaneRenderError(str(error)) from error
    store.create(SETTINGS_KEY, value, writer)
  else:
    store.replace(SETTINGS_KEY, current["revision"], value, writer)
  return color


def render_lanes(
  root: Path,
  *,
  lane: str | None = None,
  links: bool = False,
) -> tuple[str, ...]:
  selection = LaneSelectionStore(root).read().value
  if selection is None:
    raise LaneRenderError("lane selection is missing")

  assignments: dict[str, list[str]] = {}
  for issue, name in selection.assignment.items():
    assignments.setdefault(name, []).append(issue)
  for issues in assignments.values():
    issues.sort(key=int)
  names = sorted(assignments, key=_lane_key)
  if lane is not None:
    lane = lane.upper()
    if lane not in assignments:
      raise LaneRenderError(f"unknown selected lane: {lane}")
    names = [lane]

  metadata = _metadata(root, selection.closure, links)
  roots = set(selection.roots)
  annotation_width = {
    name: max(
      (len(("*" if issue in roots else "") + ("✓" if metadata[issue]["closed"] else ""))
       for issue in assignments[name]),
      default=0,
    )
    for name in names
  }
  issue_width = {
    name: max((len(issue) for issue in assignments[name]), default=1)
    for name in names
  }

  lines: list[str] = []
  for name in names:
    for issue in assignments[name]:
      annotation = (
        ("*" if issue in roots else "")
        + ("✓" if metadata[issue]["closed"] else "")
      )
      prefix = annotation.rjust(annotation_width[name])
      identifier = f"{name}.{issue.rjust(issue_width[name])}"
      text = f"{prefix}{identifier}"
      title = metadata[issue]["title"]
      if title:
        text += f"  {title}"
      if links:
        text += f"  {metadata[issue]['link']}"
      lines.append(text)
  return tuple(lines)


def _metadata(root: Path, issues: tuple[str, ...], links: bool) -> dict[str, dict]:
  config = resolve_info_config(root)
  result: dict[str, dict] = {}
  for issue in issues:
    value = issue_info(root, config, int(issue))
    result[issue] = {
      "title": value["title"],
      "closed": value["state"] == "closed",
      "link": value["link"],
    }
  return result


def _lane_key(value: str) -> tuple[int, ...]:
  return tuple(ord(char) - ord("A") for char in value)
