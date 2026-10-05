from __future__ import annotations

import unittest

from repo_workflow.lane_routes import plan_routes
from repo_workflow.lane_selection import LaneSelection


def selection(*issues: int, root: int) -> LaneSelection:
  values = tuple(str(issue) for issue in issues)
  return LaneSelection(
    roots=(str(root),),
    closure=values,
    graph_revision=0,
    assignment={str(issue): "A" for issue in issues},
  )


def layout(depths: dict[str, int]):
  columns = sorted(set(depths.values()))
  starts = {column: column * 8 for column in columns}
  widths = {column: 3 for column in columns}
  labels = {issue: f"A.{issue}" for issue in depths}
  return starts, widths, labels


class LaneRouteTests(unittest.TestCase):
  def test_direct_bypass_and_transitive_chain_keep_exact_edge_identity(self):
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1", "2"),
    }
    depths = {"1": 0, "2": 1, "3": 2}
    starts, widths, labels = layout(depths)

    plan = plan_routes(
      selection(1, 2, 3, root=3),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    identities = [(route.source, route.target) for route in plan.routes]
    self.assertEqual(
      identities,
      [("1", "2"), ("1", "3"), ("2", "3")],
    )
    self.assertEqual(len(set(identities)), len(identities))

    by_edge = {
      (route.source, route.target): route
      for route in plan.routes
    }
    self.assertEqual(by_edge[("1", "2")].kind, "primary")
    self.assertEqual(by_edge[("2", "3")].kind, "primary")
    self.assertTrue(by_edge[("1", "3")].kind.startswith("bypass["))

  def test_fan_in_preserves_both_sources_as_distinct_routes(self):
    dependencies = {
      "1": (),
      "2": (),
      "3": ("1", "2"),
    }
    depths = {"1": 0, "2": 0, "3": 1}
    starts, widths, labels = layout(depths)

    plan = plan_routes(
      selection(1, 2, 3, root=3),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    self.assertEqual(
      {(route.source, route.target) for route in plan.routes},
      {("1", "3"), ("2", "3")},
    )
    self.assertEqual(len(plan.routes), 2)

  def test_fan_out_preserves_both_targets_as_distinct_routes(self):
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1",),
    }
    depths = {"1": 0, "2": 1, "3": 1}
    starts, widths, labels = layout(depths)

    plan = plan_routes(
      LaneSelection(
        roots=("2", "3"),
        closure=("1", "2", "3"),
        graph_revision=0,
        assignment={"1": "A", "2": "A", "3": "A"},
      ),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    self.assertEqual(
      {(route.source, route.target) for route in plan.routes},
      {("1", "2"), ("1", "3")},
    )
    self.assertEqual(len(plan.routes), 2)

  def test_multiple_skip_edges_receive_unique_bypass_tracks(self):
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1", "2"),
      "4": ("1", "2", "3"),
    }
    depths = {"1": 0, "2": 1, "3": 2, "4": 3}
    starts, widths, labels = layout(depths)

    plan = plan_routes(
      selection(1, 2, 3, 4, root=4),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    bypasses = [
      route
      for route in plan.routes
      if route.kind.startswith("bypass[")
    ]
    self.assertEqual(
      {(route.source, route.target) for route in bypasses},
      {("1", "3"), ("1", "4"), ("2", "4")},
    )
    tracks = [route.track_y for route in bypasses]
    self.assertEqual(len(tracks), len(set(tracks)))

  def test_route_plan_is_deterministic_for_identical_semantic_input(self):
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1", "2"),
    }
    depths = {"1": 0, "2": 1, "3": 2}
    starts, widths, labels = layout(depths)
    args = (
      selection(1, 2, 3, root=3),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    self.assertEqual(plan_routes(*args), plan_routes(*args))

  def test_zero_and_one_edge_cardinality(self):
    starts, widths, labels = layout({"1": 0})
    empty = plan_routes(
      selection(1, root=1),
      {"1": ()},
      {"1": 0},
      starts,
      widths,
      labels,
    )
    self.assertEqual(empty.routes, ())

    depths = {"1": 0, "2": 1}
    starts, widths, labels = layout(depths)
    one = plan_routes(
      selection(1, 2, root=2),
      {"1": (), "2": ("1",)},
      depths,
      starts,
      widths,
      labels,
    )
    self.assertEqual(
      [(route.source, route.target) for route in one.routes],
      [("1", "2")],
    )


if __name__ == "__main__":
  unittest.main()
