import unittest


TEST_NAMES = (
  "tests.test_lane_count",
  "tests.test_lane_selection",
  "tests.test_lane_component_selection_cli",
  "tests.test_lane_follow_grammar",
  "tests.test_lane_show_children_grammar",
  "tests.test_first_use_workflows",
  "tests.test_ticket_state",
)


def load_tests(loader, tests, pattern):
  del tests, pattern
  suite = unittest.TestSuite()
  for name in TEST_NAMES:
    suite.addTests(loader.loadTestsFromName(name))
  return suite


if __name__ == "__main__":
  unittest.main()
