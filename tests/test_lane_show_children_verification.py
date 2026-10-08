import unittest


TEST_NAMES = (
  "tests.test_lane_show_children",
  "tests.test_lane_show_children_grammar",
  "tests.test_lane_selection",
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_show_children_fetches_one_hop_without_recursive_traversal"
  ),
  (
    "tests.test_first_use_lanes.FirstUseLanesTests."
    "test_show_children_support_fetch_does_not_expand_projection"
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
