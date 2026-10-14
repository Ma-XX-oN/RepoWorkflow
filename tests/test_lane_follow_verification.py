import unittest


TEST_NAMES = (
  "tests.test_lane_traversal",
  "tests.test_lane_follow_grammar",
  "tests.test_lane_decomposition",
  "tests.test_lane_selection",
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_group_boundary_stops_provider_component_until_followed"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_refresh_preserves_consumed_follow_budget"
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
