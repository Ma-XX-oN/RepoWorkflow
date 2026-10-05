from __future__ import annotations

import unittest

from repo_workflow.lane_routes import plan_routes, render_route_cell
from repo_workflow.lane_selection import LaneSelection


class LaneRouteTests(unittest.TestCase):
  def selection(self, issues: tuple[str, ...]) -> LaneSelection:
    return LaneSelection(
      roots=(issues[-1],),
      closure=issues,
      graph_revision=1,
      assignment={issue: "A" for issue in issues},
    )

  def layout(self, issues: tuple[str, ...], depths: dict[str, int]):
    widths = {depth: 5 for depth in set(depths.values())}
    starts = {}
    cursor = 0
    for depth in sorted(widths):
      starts[depth] = cursor
      cursor += widths[depth] + 5
    labels = {issue: f"A.{issue}" for issue in issues}
    return starts, widths, labels

  def test_direct_bypass_has_distinct_route_identity(self):
    issues = ("145", "185", "216")
    dependencies = {
      "145": (),
      "185": ("145",),
      "216": ("145", "185"),
    }
    depths = {"145": 0, "185": 1, "216": 2}
    starts, widths, labels = self.layout(issues, depths)

    plan = plan_routes(
      self.selection(issues),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )

    identities = [(route.source, route.target) for route in plan.routes]
    self.assertEqual(
      identities,
      [("145", "185"), ("145", "216"), ("185", "216")],
    )
    kinds = {
      (route.source, route.target): route.kind
      for route in plan.routes
    }
    self.assertEqual(kinds[("145", "185")], "primary")
    self.assertEqual(kinds[("185", "216")], "primary")
    self.assertTrue(kinds[("145", "216")].startswith("bypass["))
    bypass = next(
      route for route in plan.routes
      if (route.source, route.target) == ("145", "216")
    )
    self.assertIsNotNone(bypass.track_y)
    self.assertGreater(
      bypass.track_y,
      max(y for _, y in plan.positions.values()),
    )

  def test_every_semantic_edge_has_exactly_one_route(self):
    issues = ("1", "2", "3", "4", "5")
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1",),
      "4": ("1", "2", "3"),
      "5": ("2", "4"),
    }
    depths = {"1": 0, "2": 1, "3": 1, "4": 2, "5": 3}
    starts, widths, labels = self.layout(issues, depths)

    plan = plan_routes(
      self.selection(issues),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )
    expected = sorted(
      (source, target)
      for target, sources in dependencies.items()
      for source in sources
    )
    actual = sorted((route.source, route.target) for route in plan.routes)
    self.assertEqual(actual, expected)
    self.assertEqual(len(actual), len(set(actual)))

  def test_fan_in_and_fan_out_keep_all_edge_identities(self):
    issues = ("1", "2", "3", "4")
    dependencies = {
      "1": (),
      "2": ("1",),
      "3": ("1",),
      "4": ("2", "3"),
    }
    depths = {"1": 0, "2": 1, "3": 1, "4": 2}
    starts, widths, labels = self.layout(issues, depths)

    plan = plan_routes(
      self.selection(issues),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )
    self.assertEqual(
      {
        (route.source, route.target)
        for route in plan.routes
      },
      {("1", "2"), ("1", "3"), ("2", "4"), ("3", "4")},
    )

  def test_nested_long_bypasses_get_distinct_tracks(self):
    issues = ("77", "78", "99", "100")
    dependencies = {
      "77": (),
      "78": ("77",),
      "99": ("78",),
      "100": ("77", "78", "99"),
    }
    depths = {"77": 0, "78": 1, "99": 2, "100": 3}
    starts, widths, labels = self.layout(issues, depths)

    plan = plan_routes(
      self.selection(issues),
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
      {("77", "100"), ("78", "100")},
    )
    tracks = [route.track_y for route in bypasses]
    self.assertEqual(len(tracks), len(set(tracks)))
    self.assertTrue(all(track is not None for track in tracks))

  def test_unrelated_route_crossing_is_not_rendered_as_junction(self):
    self.assertEqual(
      render_route_cell({
        ("1", "4"): 1 | 2,
        ("2", "5"): 4 | 8,
      }),
      "╳",
    )

  def test_same_source_or_target_may_form_visible_junction(self):
    shared_source = render_route_cell({
      ("1", "2"): 1 | 2,
      ("1", "3"): 4 | 8,
    })
    shared_target = render_route_cell({
      ("1", "3"): 1 | 2,
      ("2", "3"): 4 | 8,
    })
    self.assertNotEqual(shared_source, "╳")
    self.assertNotEqual(shared_target, "╳")

  def test_route_plan_is_deterministic(self):
    issues = ("145", "185", "216")
    dependencies = {
      "145": (),
      "185": ("145",),
      "216": ("145", "185"),
    }
    depths = {"145": 0, "185": 1, "216": 2}
    starts, widths, labels = self.layout(issues, depths)
    first = plan_routes(
      self.selection(issues),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )
    second = plan_routes(
      self.selection(issues),
      dependencies,
      depths,
      starts,
      widths,
      labels,
    )
    self.assertEqual(first, second)


if __name__ == "__main__":
  unittest.main()
