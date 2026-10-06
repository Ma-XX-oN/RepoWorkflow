import unittest

from repo_workflow.lane_graph_adapter import (
  LaneGraphProjectionError,
  make_lane_formatter,
  project_lane_graph,
)
from repo_workflow.graph_render_model import FormatEntry
from repo_workflow.lane_selection import LaneSelection
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships(None, (), tuple(str(x) for x in deps), (), None)


def colour(name):
  def apply(text: str) -> str:
    return f"<{name}>{text}</{name}>"
  return apply


RED = colour("red")
BLUE = colour("blue")
GREY = colour("grey")


class LaneGraphAdapterTests(unittest.TestCase):
  def metadata(self, *issues):
    return {
      str(issue): {"closed": False, "title": "", "link": ""}
      for issue in issues
    }

  def test_structural_twins_project_to_one_sibling_group(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(),
      "3": relation(1, 2),
    })
    selection = LaneSelection(
      roots=("3",),
      closure=("1", "2", "3"),
      graph_revision=1,
      assignment={"1": "A", "2": "B", "3": "A"},
    )
    projection = project_lane_graph(
      selection,
      graph,
      {"1", "2", "3"},
      self.metadata(1, 2, 3),
      lane_colours={"A": RED, "B": BLUE},
      default_edge_colour=GREY,
      display_width=len,
    )
    groups = [set(group.nodes) for group in projection.graph.siblings]
    self.assertIn({"A.1", "B.2"}, groups)
    self.assertIn({"*A.3"}, groups)

  def test_lane_path_is_reconstructed_in_dependency_order(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(1),
      "3": relation(1, 2),
    })
    selection = LaneSelection(
      roots=("3",),
      closure=("1", "2", "3"),
      graph_revision=1,
      assignment={"1": "A", "2": "A", "3": "A"},
    )
    projection = project_lane_graph(
      selection,
      graph,
      {"1", "2", "3"},
      self.metadata(1, 2, 3),
      lane_colours={"A": RED},
      default_edge_colour=GREY,
      display_width=len,
    )
    self.assertEqual(
      projection.graph.lanes[0].nodes,
      ("A.1", "A.2", "*A.3"),
    )

  def test_lane_with_missing_intermediate_path_node_is_error(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(1),
      "3": relation(2),
    })
    selection = LaneSelection(
      roots=("3",),
      closure=("1", "2", "3"),
      graph_revision=1,
      assignment={"1": "A", "2": "B", "3": "A"},
    )
    with self.assertRaisesRegex(
      LaneGraphProjectionError,
      "omits an intermediate",
    ):
      project_lane_graph(
        selection,
        graph,
        {"1", "2", "3"},
        self.metadata(1, 2, 3),
        lane_colours={"A": RED, "B": BLUE},
        default_edge_colour=GREY,
        display_width=len,
      )

  def test_formatter_colours_data_but_not_annotations(self):
    formatter = make_lane_formatter(len)
    result = formatter((
      FormatEntry("*✓A.9", RED),
      FormatEntry("B.54", BLUE),
    ))
    self.assertEqual(result.display_width, 6)
    self.assertEqual(
      result.strings,
      (
        "*✓<red>A. 9</red>",
        "  <blue>B.54</blue>",
      ),
    )


if __name__ == "__main__":
  unittest.main()
