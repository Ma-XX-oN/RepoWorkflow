from pathlib import Path
import unittest

from repo_workflow.lane_decomposition import decompose_lanes
from repo_workflow.lane_graph_adapter import (
  LaneGraphProjectionError,
  make_lane_formatter,
  project_lane_graph,
)
from repo_workflow.graph_render import render_graph
from repo_workflow.graph_render_model import FormatEntry, validate_graph
from repo_workflow.lane_selection import LaneSelection
from repo_workflow.relationship_store import RelationshipStore
from repo_workflow.relationships import IssueRelationships, RelationshipGraph


def relation(*deps: int) -> IssueRelationships:
  return IssueRelationships("Issue", tuple(str(x) for x in deps))


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
    self.assertIn({"A1", "B2"}, groups)
    self.assertIn({"*A3"}, groups)

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
      ("A1", "A2", "*A3"),
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

  def test_transitive_reduction_preserves_consecutive_lane_edge(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(1),
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
    self.assertEqual(
      projection.graph.lanes[0].nodes,
      ("A1", "*A3"),
    )
    edges = {
      (source, target)
      for group in projection.graph.siblings
      for source in group.nodes
      for target_group in group.to_nodes
      for target in target_group.nodes
    }
    self.assertIn(("A1", "*A3"), edges)
    self.assertIn(("A1", "B2"), edges)
    self.assertIn(("B2", "*A3"), edges)
    validate_graph(projection.graph)

  def test_repository_shaped_139_140_143_lane_edge_survives_reduction(self):
    graph = RelationshipGraph(issues={
      "137": relation(),
      "138": relation(),
      "139": relation(137),
      "140": relation(138, 139),
      "143": relation(138, 139, 140),
    })
    selection = LaneSelection(
      roots=("143",),
      closure=("137", "138", "139", "140", "143"),
      graph_revision=1,
      assignment={
        "137": "A",
        "138": "B",
        "139": "A",
        "140": "B",
        "143": "A",
      },
    )
    projection = project_lane_graph(
      selection,
      graph,
      set(selection.closure),
      self.metadata(137, 138, 139, 140, 143),
      lane_colours={"A": RED, "B": BLUE},
      default_edge_colour=GREY,
      display_width=len,
    )
    self.assertEqual(
      projection.graph.lanes[0].nodes,
      ("A137", "A139", "*A143"),
    )
    validate_graph(projection.graph)

  def test_repository_typed_ticket_selection_projects_successfully(self):
    root = Path(__file__).resolve().parents[1]
    graph = RelationshipStore(root).read().graph
    prefixes = ("Initiative:", "Epic:", "Feature:")
    selected = tuple(
      issue
      for issue, relation in graph.issues.items()
      if relation.title.startswith(prefixes)
    )
    plan = decompose_lanes(graph, selected)
    assignment = {
      issue: lane.name
      for lane in plan.lanes
      for issue in lane.issues
    }
    selection = LaneSelection(
      roots=plan.selected,
      closure=plan.closure,
      graph_revision=1,
      assignment=assignment,
    )
    metadata = {
      issue: {
        "closed": False,
        "title": graph.issue(issue).title,
        "link": "",
      }
      for issue in plan.closure
    }
    lane_colours = {
      lane.name: RED
      for lane in plan.lanes
    }
    projection = project_lane_graph(
      selection,
      graph,
      set(plan.closure),
      metadata,
      lane_colours=lane_colours,
      default_edge_colour=GREY,
      display_width=len,
    )
    validate_graph(projection.graph)
    render_graph(projection.graph)

  def test_fan_out_fan_in_bridge_does_not_create_false_reachability(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(),
      "3": relation(2),
      "4": relation(1, 3),
      "5": relation(3),
    })
    selection = LaneSelection(
      roots=("4", "5"),
      closure=("1", "2", "3", "4", "5"),
      graph_revision=1,
      assignment={
        "1": "A",
        "2": "B",
        "3": "B",
        "4": "A",
        "5": "B",
      },
    )
    projection = project_lane_graph(
      selection,
      graph,
      set(selection.closure),
      self.metadata(1, 2, 3, 4, 5),
      lane_colours={"A": RED, "B": BLUE},
      default_edge_colour=GREY,
      display_width=len,
    )
    rendered = render_graph(projection.graph)
    self.assertEqual(
      {
        (route.source, route.target)
        for route in rendered.routes
      },
      {
        ("A1", "*A4"),
        ("B2", "B3"),
        ("B3", "*A4"),
        ("B3", "*B5"),
      },
    )

  def test_projection_removes_only_redundant_direct_edges(self):
    graph = RelationshipGraph(issues={
      "127": relation(),
      "77": relation(127),
      "78": relation(77),
      "99": relation(78),
      "100": relation(99),
      "101": relation(99, 100),
      "145": relation(77, 101),
      "185": relation(77, 145, 186),
      "186": relation(189),
      "189": relation(99),
      "208": relation(),
      "216": relation(145, 185, 208),
      "217": relation(216),
      "218": relation(217),
    })
    selection = LaneSelection(
      roots=("218",),
      closure=(
        "77", "78", "99", "100", "101", "127", "145",
        "185", "186", "189", "208", "216", "217", "218",
      ),
      graph_revision=1,
      assignment={
        "127": "A", "77": "A", "78": "A", "99": "A",
        "100": "A", "101": "A", "145": "A", "185": "A",
        "216": "A", "217": "A", "218": "A",
        "189": "B", "186": "B", "208": "C",
      },
    )
    projection = project_lane_graph(
      selection,
      graph,
      set(selection.closure),
      self.metadata(*map(int, selection.closure)),
      lane_colours={"A": RED, "B": BLUE, "C": GREY},
      default_edge_colour=GREY,
      display_width=len,
    )
    edges = {
      (source, target)
      for group in projection.graph.siblings
      for source in group.nodes
      for target_group in group.to_nodes
      for target in target_group.nodes
    }
    self.assertNotIn(("A99", "A101"), edges)
    self.assertNotIn(("A77", "A145"), edges)
    self.assertNotIn(("A77", "A185"), edges)
    self.assertNotIn(("A145", "A216"), edges)
    self.assertIn(("C208", "A216"), edges)
    self.assertIn(("B186", "A185"), edges)

  def test_reduced_projection_preserves_reachability(self):
    graph = RelationshipGraph(issues={
      "1": relation(),
      "2": relation(1),
      "3": relation(1, 2),
      "4": relation(1, 2, 3),
    })
    selection = LaneSelection(
      roots=("4",),
      closure=("1", "2", "3", "4"),
      graph_revision=1,
      assignment={
        "1": "A", "2": "A", "3": "A", "4": "A",
      },
    )
    projection = project_lane_graph(
      selection,
      graph,
      set(selection.closure),
      self.metadata(1, 2, 3, 4),
      lane_colours={"A": RED},
      default_edge_colour=GREY,
      display_width=len,
    )
    adjacency = {}
    for group in projection.graph.siblings:
      for source in group.nodes:
        adjacency[source] = {
          target
          for target_group in group.to_nodes
          for target in target_group.nodes
        }

    def reachable(source):
      pending = list(adjacency[source])
      seen = set()
      while pending:
        node = pending.pop()
        if node in seen:
          continue
        seen.add(node)
        pending.extend(adjacency[node] - seen)
      return seen

    self.assertEqual(reachable("A1"), {"A2", "A3", "*A4"})
    self.assertEqual(reachable("A2"), {"A3", "*A4"})
    self.assertEqual(reachable("A3"), {"*A4"})

  def test_formatter_colours_data_but_not_status_annotations(self):
    formatter = make_lane_formatter(len)
    result = formatter((
      FormatEntry("*✓E:A9", RED),
      FormatEntry("B54", BLUE),
    ))
    self.assertEqual(result.display_width, 7)
    self.assertEqual(
      result.strings,
      (
        "*✓<red>E:A 9</red>",
        "  <blue>  B54</blue>",
      ),
    )

  def test_untyped_column_does_not_reserve_type_prefix_space(self):
    formatter = make_lane_formatter(len)
    result = formatter((
      FormatEntry("A9", RED),
      FormatEntry("B54", BLUE),
    ))
    self.assertEqual(result.display_width, 3)
    self.assertEqual(
      result.strings,
      (
        "<red>A 9</red>",
        "<blue>B54</blue>",
      ),
    )

  def test_title_prefixes_annotate_projected_node_ids(self):
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
    metadata = {
      "1": {"closed": False, "title": "Initiative: One", "link": ""},
      "2": {"closed": False, "title": "Feature: Two", "link": ""},
      "3": {"closed": False, "title": "Epic: Three", "link": ""},
    }
    projection = project_lane_graph(
      selection,
      graph,
      set(selection.closure),
      metadata,
      lane_colours={"A": RED, "B": BLUE},
      default_edge_colour=GREY,
      display_width=len,
    )
    nodes = {
      node
      for group in projection.graph.siblings
      for node in group.nodes
    }
    self.assertEqual(nodes, {"I:A1", "F:B2", "*E:A3"})


if __name__ == "__main__":
  unittest.main()
