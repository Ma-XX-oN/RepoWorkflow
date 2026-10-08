import unittest


TEST_NAMES = (
  "tests.test_lane_projection",
  "tests.test_lane_selection",
  "tests.test_lane_projection_cli",
  "tests.test_lane_relationship_coverage",
  "tests.test_lane_count",
  "tests.test_lane_graph_adapter",
  "tests.test_lane_render",
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_dependencies_mode_fetches_only_dependency_direction"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_dependents_mode_does_not_reverse_through_dependency_support"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_default_both_is_union_without_direction_reversal"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_directional_selection_refresh_replays_persisted_rules"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_partial_single_cache_widens_to_dependents_without_refresh"
  ),
)


def load_tests(loader, tests, pattern):
  del tests, pattern
  suite = unittest.TestSuite()
  for name in TEST_NAMES:
    suite.addTests(loader.loadTestsFromName(name))
  return suite


if __name__ == "__main__":
  unittest.main()
