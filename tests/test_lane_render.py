from pathlib import Path
import re
import tempfile
import unittest

from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_render import (
  LaneRenderError,
  color_setting,
  render_lanes,
  set_color_setting,
)
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.lifecycle_store import LifecycleStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(x) for x in deps))


def _strip_terminal(value: str) -> str:
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

  def test_status_annotations_touch_identifier_and_lane_letters_align(self):
    lines = render_lanes(self.root)
    line_9 = next(line for line in lines if "A 9" in line)
    line_54 = next(line for line in lines if "?B54" in line)
    self.assertEqual(line_9.index("A"), line_54.index("B"))
    self.assertIn("?A 9", line_9)
    self.assertIn("?B54", line_54)
    self.assertTrue(any("*?A107" in line for line in lines))
    graph = "\n".join(lines)
    self.assertIn("─", graph)
    self.assertTrue(any(char in graph for char in "┬┐┴┘├┤┼"))

  def test_independent_roots_are_each_rendered_once(self):
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

    rendered = "\n".join(render_lanes(self.root))
    self.assertEqual(rendered.count("*?A63"), 1)
    self.assertEqual(rendered.count("*?B65"), 1)
    self.assertNotIn("─", rendered)

  def test_titles_do_not_change_graph_geometry(self):
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
    self.assertLess(rendered.index("A1"), rendered.index("A2"))
    self.assertLess(rendered.index("A2"), rendered.index("*?A3"))
    self.assertGreaterEqual(rendered.count("─"), 2)

  def test_fan_out_does_not_duplicate_source(self):
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

    rendered = "\n".join(render_lanes(self.root))
    self.assertEqual(rendered.count("A1"), 1)
    self.assertIn("*?A2", rendered)
    self.assertIn("*?B3", rendered)

  def test_redundant_long_dependency_is_not_displayed(self):
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
    rendered = "\n".join(
      render_lanes(self.root, diagnostics=diagnostics)
    )
    for value in ("A145", "A185", "*?A216"):
      self.assertIn(value, rendered)
    routes = {
      (item["source"], item["target"])
      for item in diagnostics.routed_edges
    }
    self.assertEqual(routes, {(145, 185), (185, 216)})
    self.assertNotIn((145, 216), routes)

  def test_graph_rejects_titles_and_links(self):
    with self.assertRaisesRegex(LaneRenderError, "lanes list"):
      render_lanes(self.root, links=True)
    with self.assertRaisesRegex(LaneRenderError, "lanes list"):
      render_lanes(self.root, titles=True)

  def test_single_lane_filter_preserves_node_label(self):
    self.assertEqual(render_lanes(self.root, lane="B"), ("?B54",))

  def test_color_setting_defaults_and_persists(self):
    self.assertEqual(color_setting(self.root), "auto")
    self.assertEqual(
      set_color_setting(self.root, "never", self.writer),
      "never",
    )
    self.assertEqual(color_setting(self.root), "never")
    self.assertEqual(
      set_color_setting(self.root, "always", self.writer),
      "always",
    )
    self.assertEqual(color_setting(self.root), "always")

  def test_never_colour_mode_is_plain(self):
    set_color_setting(self.root, "never", self.writer)
    plain = render_lanes(self.root)
    self.assertTrue(all("\x1b[" not in line for line in plain))

  def test_styling_never_changes_visible_graph(self):
    set_color_setting(self.root, "never", self.writer)
    plain = render_lanes(self.root)
    set_color_setting(self.root, "always", self.writer)
    styled = render_lanes(self.root)
    self.assertEqual(
      tuple(_strip_terminal(line) for line in styled),
      plain,
    )


  def test_default_graph_reads_saved_status_and_ignores_provider_closed(self):
    store = RelationshipStore(self.root)
    store.refresh_states(self.writer)
    before = "\\n".join(render_lanes(self.root))
    self.assertIn("○A 9", before)
    self.assertIn("○B54", before)
    self.assertIn("*○A107", before)
    lifecycle = LifecycleStore(self.root)
    started = lifecycle.transition(
      9, "start", "candidate-9", 0, self.writer, None,
    )
    self.assertEqual(started.lifecycle.state, "active")
    self.assertEqual("\\n".join(render_lanes(self.root)), before)
    store.refresh_states(self.writer)
    refreshed = "\\n".join(render_lanes(self.root))
    self.assertIn("●A 9", refreshed)
    self.assertIn("○B54", refreshed)

  def test_all_six_lifecycle_glyphs_render_from_csv(self):
    from repo_workflow.lane_graph_adapter import _STATE_GLYPHS
    self.assertEqual(
      _STATE_GLYPHS,
      {
        "not_started": "○",
        "active": "●",
        "in_review": "◎",
        "accepted": "✓",
        "completed": "♥",
        "aborted": "✕",
      },
    )

  def test_invalid_color_fails(self):
    with self.assertRaisesRegex(Exception, "auto, always, or never"):
      set_color_setting(self.root, "sometimes", self.writer)


if __name__ == "__main__":
  unittest.main()
