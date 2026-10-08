import unittest


TEST_NAMES = (
  "tests.test_lane_follow_activation",
  "tests.test_lane_traversal",
  "tests.test_lane_decomposition",
  "tests.test_lane_selection",
  "tests.test_lane_show_children",
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_no_follow_keeps_provider_support_out_of_projection"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_group_boundary_stops_provider_component_until_followed"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_show_children_fetches_one_hop_without_recursive_traversal"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_select_add_remove_preserve_distinct_root_semantics"
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
