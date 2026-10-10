from __future__ import annotations

from pathlib import Path

from .graph_render import GraphLayoutError, render_graph
from .graph_render_model import GraphInputError
from .issue_metadata import IssueMetadataStore
from .lane_graph_adapter import (
  LaneGraphProjectionError,
  project_lane_graph,
)
from .lane_selection import LaneSelectionStore
from .relationship_store import RelationshipStore
from .state_store import StateStoreError, WriterIdentity, clone_local_store
from .terminal_style import TerminalStyler


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
  titles: bool = False,
  diagnostics=None,
) -> tuple[str, ...]:
  if links or titles:
    raise LaneRenderError(
      "graph view does not render titles or links; use lanes list"
    )

  selection = LaneSelectionStore(root).read().value
  if selection is None:
    raise LaneRenderError("lane selection is missing")
  snapshot = RelationshipStore(root).read()
  relationship_graph = snapshot.graph

  visible = set(selection.closure)
  if lane is not None:
    requested = lane.upper()
    if requested not in set(selection.assignment.values()):
      raise LaneRenderError(f"unknown selected lane: {requested}")
    visible = {
      issue
      for issue in selection.closure
      if selection.assignment[issue] == requested
    }

  metadata = _metadata(root, tuple(sorted(visible, key=int)))
  for issue in visible:
    state = None if snapshot.states is None else snapshot.states[issue].state
    metadata[issue]["lifecycle_state"] = state
  styler = TerminalStyler(color_setting(root))
  lane_colours = {
    lane_name: styler.lane_colour(lane_name)
    for lane_name in set(selection.assignment.values())
  }

  try:
    projection = project_lane_graph(
      selection,
      relationship_graph,
      visible,
      metadata,
      lane_colours=lane_colours,
      default_edge_colour=styler.default_edge_colour(),
      display_width=styler.display_width,
    )
    result = render_graph(projection.graph)
  except (GraphInputError, GraphLayoutError, LaneGraphProjectionError) as error:
    raise LaneRenderError(str(error)) from error

  if diagnostics is not None:
    issue_by_text = {
      text: int(issue)
      for issue, text in projection.issue_text.items()
    }
    diagnostics.routed_edges = [
      _diagnostic(route.diagnostic(), issue_by_text)
      for route in result.routes
    ]

  return result.lines


def _diagnostic(value: dict, issue_by_text: dict[str, int]) -> dict:
  result = dict(value)
  result["source"] = issue_by_text[value["source"]]
  result["target"] = issue_by_text[value["target"]]
  return result


def _metadata(root: Path, issues: tuple[str, ...]) -> dict[str, dict]:
  store = IssueMetadataStore(root)
  result: dict[str, dict] = {}
  for issue in issues:
    value = store.display_issue(int(issue))
    result[issue] = {
      "title": value.title,
      "closed": value.state == "closed",
      "link": value.link,
    }
  return result
