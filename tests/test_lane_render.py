from pathlib import Path
import tempfile
import unittest

from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_render import (
  color_setting,
  render_lanes,
  set_color_setting,
)
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships(None, (), tuple(str(x) for x in deps), (), None)


def _strip_ansi(value: str) -> str:
  import re
  return re.sub(r"\x1b\[[0-9;]*m", "", value)


class LaneRenderTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.root = Path(self.temp.name) / "repo"
    self.root.mkdir()
    RepoFixture(self.root)
    self.writer = WriterIdentity("agent", "session")
    RelationshipStore(self.root).create(
      RelationshipGraph(issues={
        "9": relation(),
        "54": relation(),
        "107": relation(9, 54),
      }),
      self.writer,
    )
    LaneSelectionStore(self.root).select((107,), self.writer)
    self.write_metadata({
      9: ("Issue 9", "closed"),
      54: ("Issue 54", "open"),
      107: ("Issue 107", "closed"),
    })

  def tearDown(self):
    self.temp.cleanup()

  def write_metadata(self, values: dict[int, tuple[str, str]]) -> None:
    IssueMetadataStore(self.root).write(
      {
        number: IssueMetadata(
          number=number,
          title=title,
          state=state,
          link=f"https://example.invalid/issues/{number}",
        )
        for number, (title, state) in values.items()
      },
      self.writer,
    )

  def test_annotations_touch_identifier_and_decimal_align(self):
    lines = render_lanes(self.root)
    line_9 = next(line for line in lines if "A. 9" in line)
    line_54 = next(line for line in lines if "B.54" in line)
    self.assertEqual(line_9.index("."), line_54.index("."))
    self.assertIn("✓A. 9", line_9)
    self.assertIn(" B.54", line_54)
    self.assertTrue(any("*✓A.107" in line for line in lines))
    graph = "\n".join(lines)
    self.assertIn("─", graph)
    self.assertTrue(any(char in graph for char in "┬┐┴┘├┤┼"))

  def test_independent_roots_match_compact_alignment_contract(self):
    graph_store = RelationshipStore(self.root)
    graph = graph_store.read()
    graph_store.replace(
      graph.revision,
      RelationshipGraph(issues={
        "63": relation(),
        "65": relation(),
      }),
      self.writer,
    )
    selection_store = LaneSelectionStore(self.root)
    selection = selection_store.read()
    selection_store.select(
      (63, 65),
      self.writer,
      expected_revision=selection.revision,
    )
    self.write_metadata({
      63: ("Define portable repo-info read contract", "closed"),
      65: ("Define provider-neutral repo-ci contract", "open"),
    })

    self.assertEqual(
      render_lanes(self.root),
      (
        "*✓A.63",
        " *B.65",
      ),
    )

  def test_titles_do_not_change_compact_graph_geometry(self):
    short = render_lanes(self.root)
    self.write_metadata({
      9: (
        "Extremely long issue title that must not affect graph topology for 9",
        "closed",
      ),
      54: (
        "Extremely long issue title that must not affect graph topology for 54",
        "open",
      ),
      107: (
        "Extremely long issue title that must not affect graph topology for 107",
        "closed",
      ),
    })
    self.assertEqual(render_lanes(self.root), short)

  def test_three_column_chain_renders_leaf_to_root(self):
    graph_store = RelationshipStore(self.root)
    current_graph = graph_store.read()
    graph_store.replace(
      current_graph.revision,
      RelationshipGraph(issues={
        "1": relation(),
        "2": relation(1),
        "3": relation(2),
      }),
      self.writer,
    )
    selection_store = LaneSelectionStore(self.root)
    current_selection = selection_store.read()
    selection_store.select(
      (3,),
      self.writer,
      expected_revision=current_selection.revision,
    )
    self.write_metadata({
      1: ("Issue 1", "open"),
      2: ("Issue 2", "open"),
      3: ("Issue 3", "open"),
    })

    rendered = "\n".join(render_lanes(self.root))
    self.assertLess(rendered.index("A.1"), rendered.index("A.2"))
    self.assertLess(rendered.index("A.2"), rendered.index("*A.3"))
    self.assertGreaterEqual(rendered.count("─"), 2)

  def test_fan_out_uses_branch_connectors_without_duplicating_source(self):
    graph_store = RelationshipStore(self.root)
    current_graph = graph_store.read()
    graph_store.replace(
      current_graph.revision,
      RelationshipGraph(issues={
        "1": relation(),
        "2": relation(1),
        "3": relation(1),
      }),
      self.writer,
    )
    selection_store = LaneSelectionStore(self.root)
    current_selection = selection_store.read()
    selection_store.select(
      (2, 3),
      self.writer,
      expected_revision=current_selection.revision,
    )
    self.write_metadata({
      1: ("Issue 1", "open"),
      2: ("Issue 2", "open"),
      3: ("Issue 3", "open"),
    })

    lines = render_lanes(self.root)
    rendered = "\n".join(lines)
    self.assertEqual(rendered.count("A.1"), 1)
    self.assertIn("*A.2", rendered)
    self.assertIn("*A.3", rendered)
    self.assertTrue(any(char in rendered for char in "┬┐┴┘├┤┼"))

  def test_direct_dependency_bypass_is_visually_separate_and_diagnostic(self):
    graph_store = RelationshipStore(self.root)
    current_graph = graph_store.read()
    graph_store.replace(
      current_graph.revision,
      RelationshipGraph(issues={
        "145": relation(),
        "185": relation(145),
        "216": relation(145, 185),
      }),
      self.writer,
    )
    selection_store = LaneSelectionStore(self.root)
    current_selection = selection_store.read()
    selection_store.select(
      (216,),
      self.writer,
      expected_revision=current_selection.revision,
    )
    self.write_metadata({
      145: ("Issue 145", "closed"),
      185: ("Issue 185", "closed"),
      216: ("Issue 216", "open"),
    })

    class Diagnostics:
      routed_edges = []

    diagnostics = Diagnostics()
    lines = render_lanes(self.root, diagnostics=diagnostics)
    rendered = "\n".join(lines)

    self.assertIn("A.145", rendered)
    self.assertIn("A.185", rendered)
    self.assertIn("*A.216", rendered)
    self.assertGreaterEqual(len(lines), 2)
    self.assertEqual(
      {
        (item["source"], item["target"])
        for item in diagnostics.routed_edges
      },
      {(145, 185), (145, 216), (185, 216)},
    )
    bypass = next(
      item
      for item in diagnostics.routed_edges
      if (item["source"], item["target"]) == (145, 216)
    )
    self.assertTrue(bypass["kind"].startswith("bypass["))
    self.assertIn("track_y", bypass)
    self.assertTrue(
      any(
        "A.145" not in line
        and "A.185" not in line
        and "A.216" not in line
        and "─" in line
        for line in lines
      )
    )

  def test_links_are_optional(self):
    self.assertTrue(all("https://" not in x for x in render_lanes(self.root)))
    linked = render_lanes(self.root, links=True)
    self.assertEqual(sum(line.count("https://") for line in linked), 3)

  def test_single_lane_filter_preserves_column_width_rules(self):
    self.assertEqual(render_lanes(self.root, lane="B"), ("B.54",))

  def test_color_setting_defaults_and_persists(self):
    self.assertEqual(color_setting(self.root), "auto")
    self.assertEqual(set_color_setting(self.root, "never", self.writer), "never")
    self.assertEqual(color_setting(self.root), "never")
    self.assertEqual(set_color_setting(self.root, "always", self.writer), "always")
    self.assertEqual(color_setting(self.root), "always")

  def test_color_setting_controls_rendered_lane_tokens(self):
    set_color_setting(self.root, "never", self.writer)
    plain = render_lanes(self.root)
    self.assertTrue(all("\x1b[" not in line for line in plain))

    set_color_setting(self.root, "always", self.writer)
    colored = render_lanes(self.root)
    self.assertTrue(any("\x1b[" in line for line in colored))
    self.assertEqual(
      tuple(_strip_ansi(line) for line in colored),
      plain,
    )

  def test_invalid_color_fails(self):
    with self.assertRaisesRegex(Exception, "auto, always, or never"):
      set_color_setting(self.root, "sometimes", self.writer)


if __name__ == "__main__":
  unittest.main()
