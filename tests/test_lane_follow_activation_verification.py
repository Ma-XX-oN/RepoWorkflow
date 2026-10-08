import unittest


TEST_NAMES = (
  "tests.test_lane_follow_activation",
  "tests.test_lane_traversal",
  "tests.test_lane_decomposition",
  "tests.test_lane_selection",
  "tests.test_lane_show_children",
)


def load_tests(loader, tests, pattern):
  del tests, pattern
  suite = unittest.TestSuite()
  for name in TEST_NAMES:
    suite.addTests(loader.loadTestsFromName(name))
  return suite


if __name__ == "__main__":
  unittest.main()
