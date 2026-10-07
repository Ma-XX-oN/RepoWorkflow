from __future__ import annotations

import unittest

from repo_workflow.graph_layout import build_layout
from repo_workflow.graph_render import render_graph
from repo_workflow.graph_render_types import _D, _L, _R, _U
from repo_workflow.lane_graph_adapter import project_lane_graph
from repo_workflow.lane_selection import LaneSelection
from repo_workflow.relationships import (
  IssueRelationships,
  RelationshipGraph,
)


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(value) for value in deps))


def identity(text: str) -> str:
  return text


_GLYPH_BITS = {
  "─": _L | _R,
  "│": _U | _D,
  "↑": _U | _D,
  "↓": _U | _D,
  "┌": _R | _D,
  "┐": _L | _D,
  "└": _R | _U,
  "┘": _L | _U,
  "├": _R | _U | _D,
  "┤": _L | _U | _D,
  "┬": _L | _R | _D,
  "┴": _L | _R | _U,
  "┼": _L | _R | _U | _D,
}


class LaneDisplayReductionTests(unittest.TestCase):
  def make_218_projection(self):
    graph = RelationshipGraph(issues={
      "127": relation(),
      "77": relation(127),
      "78": relation(77),
      "99": relation(78),
      "100": relation(99),
      "101": relation(99, 100),
      "145": relation(77, 101),
      "189": relation(99),
      "186": relation(189),
      "185": relation(77, 145, 186),
      "208": relation(),
      "216": relation(145, 185, 208),
      "217": relation(216),
      "218": relation(217),
    })
    closure = (
      "77", "78", "99", "100", "101", "127", "145",
      "185", "186", "189", "208", "216", "217", "218",
    )
    selection = LaneSelection(
      roots=("218",),
      closure=closure,
      graph_revision=1,
      assignment={
        "127": "A", "77": "A", "78": "A", "99": "A",
        "100": "A", "101": "A", "145": "A", "185": "A",
        "216": "A", "217": "A", "218": "A",
        "189": "B", "186": "B", "208": "C",
      },
    )
    metadata = {
      issue: {"closed": False, "title": "", "link": ""}
      for issue in closure
    }
    return project_lane_graph(
      selection,
      graph,
      set(closure),
      metadata,
      lane_colours={
        "A": identity,
        "B": identity,
        "C": identity,
      },
      default_edge_colour=identity,
      display_width=len,
    )

  def test_real_218_reduced_routes_are_minimal_reachability_edges(self):
    projection = self.make_218_projection()
    result = render_graph(projection.graph)
    reverse = {
      text: issue
      for issue, text in projection.issue_text.items()
    }
    routes = {
      (reverse[route.source], reverse[route.target])
      for route in result.routes
    }
    self.assertEqual(
      routes,
      {
        ("127", "77"),
        ("77", "78"),
        ("78", "99"),
        ("99", "100"),
        ("100", "101"),
        ("101", "145"),
        ("99", "189"),
        ("189", "186"),
        ("186", "185"),
        ("145", "185"),
        ("185", "216"),
        ("208", "216"),
        ("216", "217"),
        ("217", "218"),
      },
    )

  def test_real_218_final_glyphs_preserve_junctions_and_horizontal_crossings(self):
    projection = self.make_218_projection()
    layout = build_layout(projection.graph)
    rendered = render_graph(projection.graph)
    lines = rendered.lines

    for (x, y), contributions in layout.cells.items():
      per_edge = {}
      bundles = set()
      for contribution in contributions:
        key = contribution.edge.key
        edge, bits = per_edge.get(
          key,
          (contribution.edge, 0),
        )
        per_edge[key] = edge, bits | contribution.bits
        bundles.add(contribution.bundle)

      values = list(per_edge.values())
      required = 0
      for _, bits in values:
        required |= bits

      if len(values) > 1:
        same_source = len({
          edge.source
          for edge, _ in values
        }) == 1
        same_target = len({
          edge.target
          for edge, _ in values
        }) == 1
        shared_bits = values[0][1]
        for _, bits in values[1:]:
          shared_bits &= bits
        intentional_junction = (
          ((same_source or same_target) and bool(shared_bits))
          or (len(bundles) == 1 and None not in bundles)
        )
        if not intentional_junction and required & (_L | _R):
          required &= _L | _R

      char = lines[y][x] if x < len(lines[y]) else " "
      visible = _GLYPH_BITS.get(char, 0)
      self.assertEqual(
        visible & required,
        required,
        (
          f"rendered glyph violates routed crossing/junction contract "
          f"at ({x}, {y}): required={required}, char={char!r}\n"
          + "\n".join(lines)
        ),
      )

  def test_real_218_has_no_adjacent_duplicate_arrow_columns(self):
    rendered = "\n".join(
      render_graph(self.make_218_projection().graph).lines
    )
    for noisy in ("↓↓", "↑↑", "↓↑", "↑↓"):
      self.assertNotIn(noisy, rendered)


if __name__ == "__main__":
  unittest.main()
