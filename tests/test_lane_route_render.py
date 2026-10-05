from pathlib import Path
import tempfile
import unittest

from repo_workflow.issue_metadata import IssueMetadata, IssueMetadataStore
from repo_workflow.lane_render import render_lanes
from repo_workflow.lane_selection import LaneSelectionStore
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph
from repo_workflow.state_store import WriterIdentity
from tests.support import RepoFixture


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships(None, (), tuple(str(x) for x in deps), (), None)


class LaneRouteRenderTests(unittest.TestCase):
  def fixture(
    self,
    issues: dict[str, IssueRelationships],
    roots: tuple[int, ...],
  ):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name) / "repo"
    root.mkdir()
    RepoFixture(root)
    writer = WriterIdentity("agent", "session")
    RelationshipStore(root).create(
      RelationshipGraph(issues=issues),
      writer,
    )
    LaneSelectionStore(root).select(roots, writer)
    IssueMetadataStore(root).write(
      {
        int(issue): IssueMetadata(
          int(issue),
          f"Issue {issue}",
          "open",
          f"https://example.invalid/issues/{issue}",
        )
        for issue in issues
      },
      writer,
    )
    return temp, root

  def test_direct_skip_edge_is_rendered_as_separate_bypass_track(self):
    temp, root = self.fixture(
      {
        "145": relation(),
        "185": relation(145),
        "216": relation(145, 185),
      },
      (216,),
    )
    self.addCleanup(temp.cleanup)

    lines = render_lanes(root)
    self.assertEqual(
      lines,
      (
        "A.145 ─┬──A.185 ──┬─*A.216",
        "       │          │",
        "       └──────────┘",
      ),
    )

  def test_fan_in_retains_parallel_path_shape(self):
    temp, root = self.fixture(
      {
        "105": relation(),
        "106": relation(),
        "107": relation(105, 106),
      },
      (107,),
    )
    self.addCleanup(temp.cleanup)

    rendered = "\n".join(render_lanes(root))
    self.assertEqual(rendered.count("A.105"), 1)
    self.assertEqual(rendered.count("B.106"), 1)
    self.assertEqual(rendered.count("*A.107"), 1)
    self.assertIn("└", rendered)
    self.assertIn("┘", rendered)

  def test_nested_direct_bypasses_have_distinct_golden_tracks(self):
    temp, root = self.fixture(
      {
        "77": relation(),
        "78": relation(77),
        "99": relation(78),
        "100": relation(77, 78, 99),
      },
      (100,),
    )
    self.addCleanup(temp.cleanup)

    class Diagnostics:
      routed_edges = []

    diagnostics = Diagnostics()
    lines = render_lanes(root, diagnostics=diagnostics)
    self.assertEqual(
      lines,
      (
        "A.77 ─┬──A.78 ─┬──A.99 ──┬─*A.100",
        "      │        │         │",
        "      └────────┼─────────┤",
        "               │         │",
        "               └─────────┘",
      ),
    )
    bypasses = {
      (item["source"], item["target"]): item
      for item in diagnostics.routed_edges
      if item["kind"].startswith("bypass[")
    }
    self.assertEqual(set(bypasses), {(77, 100), (78, 100)})
    self.assertNotEqual(
      bypasses[(77, 100)]["track_y"],
      bypasses[(78, 100)]["track_y"],
    )

  def test_disconnected_connected_components_do_not_interfere(self):
    temp, root = self.fixture(
      {
        "21": relation(),
        "22": relation(21),
        "30": relation(),
        "40": relation(30),
        "50": relation(40),
      },
      (22, 50),
    )
    self.addCleanup(temp.cleanup)

    class Diagnostics:
      routed_edges = []

    diagnostics = Diagnostics()
    rendered = "\n".join(render_lanes(root, diagnostics=diagnostics))
    self.assertNotIn("╳", rendered)
    self.assertEqual(
      {
        (item["source"], item["target"])
        for item in diagnostics.routed_edges
      },
      {(21, 22), (30, 40), (40, 50)},
    )
    for issue in ("21", "22", "30", "40", "50"):
      self.assertEqual(rendered.count(f".{issue}"), 1)


if __name__ == "__main__":
  unittest.main()
