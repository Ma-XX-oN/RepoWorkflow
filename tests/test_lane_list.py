from pathlib import Path
import re
import tempfile
import unittest

from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_list import LaneListError, render_lane_list
from repo_workflow.lane_render import set_color_setting
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(x) for x in deps))


class LaneListTests(unittest.TestCase):
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
    IssueMetadataStore(self.root).write(
      {
        9: IssueMetadata(
          9,
          "Nine",
          "closed",
          "https://example.invalid/issues/9",
        ),
        54: IssueMetadata(
          54,
          "Fifty Four",
          "open",
          "https://example.invalid/issues/54",
        ),
        107: IssueMetadata(
          107,
          "One Hundred Seven",
          "closed",
          "https://example.invalid/issues/107",
        ),
      },
      self.writer,
    )

  def tearDown(self):
    self.temp.cleanup()

  def test_list_groups_issues_by_lane_with_titles(self):
    self.assertEqual(
      render_lane_list(self.root),
      (
        "Lane A",
        "#9  Nine",
        "#107  One Hundred Seven",
        "",
        "Lane B",
        "#54  Fifty Four",
      ),
    )

  def test_groups_use_lane_colour_and_never_mode_stays_plain(self):
    set_color_setting(self.root, "always", self.writer)
    styled = render_lane_list(self.root)
    self.assertTrue(all(
      "\x1b[" in line
      for line in styled
      if line
    ))

    set_color_setting(self.root, "never", self.writer)
    plain = render_lane_list(self.root)
    self.assertTrue(all("\x1b[" not in line for line in plain))
    self.assertEqual(
      tuple(re.sub(r"\x1b\[[0-9;]*m", "", line) for line in styled),
      plain,
    )

  def test_links_are_optional(self):
    plain = render_lane_list(self.root)
    self.assertTrue(all("https://" not in line for line in plain))

    linked = render_lane_list(self.root, links=True)
    self.assertEqual(sum(line.count("https://") for line in linked), 3)

  def test_lane_filter_is_read_only_and_rejects_unknown_lane(self):
    before = LaneSelectionStore(self.root).read()
    self.assertEqual(
      render_lane_list(self.root, lane="b"),
      (
        "Lane B",
        "#54  Fifty Four",
      ),
    )
    self.assertEqual(LaneSelectionStore(self.root).read(), before)
    with self.assertRaisesRegex(LaneListError, "unknown selected lane"):
      render_lane_list(self.root, lane="Z")


if __name__ == "__main__":
  unittest.main()
