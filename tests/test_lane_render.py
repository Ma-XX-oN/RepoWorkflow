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
    self.assertEqual(lines, (
      " ✓A.  9  Issue 9",
      "*✓A.107  Issue 107",
      "B.54  Issue 54",
    ))

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

  def test_invalid_color_fails(self):
    with self.assertRaisesRegex(Exception, "auto, always, or never"):
      set_color_setting(self.root, "sometimes", self.writer)


if __name__ == "__main__":
  unittest.main()
