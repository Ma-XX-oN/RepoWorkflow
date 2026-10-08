import unittest


TEST_NAMES = (
  "tests.test_lane_terminal_root_expansion",
  "tests.test_lane_traversal",
  "tests.test_lane_decomposition",
  "tests.test_lane_count",
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_terminal_refactor_does_not_launch_provider_dependant_fanout"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_group_boundary_stops_provider_component_until_followed"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_show_children_fetches_one_hop_without_recursive_traversal"
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
