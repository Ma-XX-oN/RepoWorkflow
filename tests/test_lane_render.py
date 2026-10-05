from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

  def tearDown(self):
    self.temp.cleanup()

  def info(self, _root, _config, number):
    return {
      "schema_version": 1,
      "number": number,
      "title": f"Issue {number}",
      "state": "closed" if number in {9, 107} else "open",
      "link": f"https://example.invalid/issues/{number}",
    }

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_annotations_touch_identifier_and_decimal_align(self, info, _config):
    info.side_effect = self.info
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

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_independent_roots_match_compact_alignment_contract(self, info, _config):
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

    def independent_info(_root, _config, number):
      return {
        "schema_version": 1,
        "number": number,
        "title": {
          63: "Define portable repo-info read contract",
          65: "Define provider-neutral repo-ci contract",
        }[number],
        "state": "closed" if number == 63 else "open",
        "link": f"https://example.invalid/issues/{number}",
      }

    info.side_effect = independent_info
    self.assertEqual(
      render_lanes(self.root),
      (
        "*✓A.63  Define portable repo-info read contract",
        " *B.65  Define provider-neutral repo-ci contract",
      ),
    )

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_three_column_chain_renders_leaf_to_root(self, info, _config):
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
    info.side_effect = lambda _root, _config, number: {
      "schema_version": 1,
      "number": number,
      "title": f"Issue {number}",
      "state": "open",
      "link": f"https://example.invalid/issues/{number}",
    }

    rendered = "\n".join(render_lanes(self.root))
    self.assertLess(rendered.index("A.1"), rendered.index("A.2"))
    self.assertLess(rendered.index("A.2"), rendered.index("*A.3"))
    self.assertGreaterEqual(rendered.count("─"), 2)

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_fan_out_uses_branch_connectors_without_duplicating_source(
    self,
    info,
    _config,
  ):
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
    info.side_effect = lambda _root, _config, number: {
      "schema_version": 1,
      "number": number,
      "title": f"Issue {number}",
      "state": "open",
      "link": f"https://example.invalid/issues/{number}",
    }

    lines = render_lanes(self.root)
    rendered = "\n".join(lines)
    self.assertEqual(rendered.count("A.1"), 1)
    self.assertIn("*A.2", rendered)
    self.assertIn("*A.3", rendered)
    self.assertTrue(any(char in rendered for char in "┬┐┴┘├┤┼"))

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_links_are_optional(self, info, _config):
    info.side_effect = self.info
    self.assertTrue(all("https://" not in x for x in render_lanes(self.root)))
    self.assertTrue(all(
      "https://" in x for x in render_lanes(self.root, links=True)
    ))

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_single_lane_filter_preserves_column_width_rules(self, info, _config):
    info.side_effect = self.info
    self.assertEqual(render_lanes(self.root, lane="B"), ("B.54  Issue 54",))

  def test_color_setting_defaults_and_persists(self):
    self.assertEqual(color_setting(self.root), "auto")
    self.assertEqual(set_color_setting(self.root, "never", self.writer), "never")
    self.assertEqual(color_setting(self.root), "never")
    self.assertEqual(set_color_setting(self.root, "always", self.writer), "always")
    self.assertEqual(color_setting(self.root), "always")

  @patch("repo_workflow.lane_render.resolve_info_config", return_value={})
  @patch("repo_workflow.lane_render.issue_info")
  def test_color_setting_controls_rendered_lane_tokens(self, info, _config):
    info.side_effect = self.info
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
