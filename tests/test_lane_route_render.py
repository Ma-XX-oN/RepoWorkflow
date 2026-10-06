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

  def test_direct_skip_edge_uses_hidden_continuation(self):
    temp, root = self.fixture(
      {
        "145": relation(),
        "185": relation(145),
        "216": relation(145, 185),
      },
      (216,),
    )
    self.addCleanup(temp.cleanup)

    class Diagnostics:
      routed_edges = []

    diagnostics = Diagnostics()
    rendered = "\n".join(
      render_lanes(root, diagnostics=diagnostics)
    )
    self.assertIn("A.145", rendered)
    self.assertIn("A.185", rendered)
    self.assertIn("*A.216", rendered)

    long_route = next(
      route
      for route in diagnostics.routed_edges
      if (route["source"], route["target"]) == (145, 216)
    )
    self.assertEqual(long_route["kind"], "long")
    self.assertEqual(long_route["hidden_columns"], [1])

  def test_fan_in_keeps_sibling_nodes_compact(self):
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
    self.assertTrue(
      any(char in rendered for char in "┬┐┴┘├┤┼")
    )

  def test_direct_and_transitive_edges_keep_separate_identities(self):
    temp, root = self.fixture(
      {
        "77": relation(),
        "78": relation(77),
        "99": relation(78),
        "100": relation(77, 99),
      },
      (100,),
    )
    self.addCleanup(temp.cleanup)

    class Diagnostics:
      routed_edges = []

    diagnostics = Diagnostics()
    rendered = "\n".join(
      render_lanes(root, diagnostics=diagnostics)
    )
    for label in ("A.77", "A.78", "A.99", "*A.100"):
      self.assertIn(label, rendered)
    self.assertEqual(
      {
        (item["source"], item["target"])
        for item in diagnostics.routed_edges
      },
      {
        (77, 78),
        (77, 100),
        (78, 99),
        (99, 100),
      },
    )
    self.assertEqual(
      next(
        item
        for item in diagnostics.routed_edges
        if (item["source"], item["target"]) == (77, 100)
      )["kind"],
      "long",
    )


if __name__ == "__main__":
  unittest.main()
