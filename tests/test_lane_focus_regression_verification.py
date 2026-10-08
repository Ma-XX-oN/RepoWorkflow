import unittest


TEST_NAMES = (
  (
    "tests.test_canonical_lane_smoke.CanonicalLaneSmokeTests."
    "test_focus_seed_413_preserves_canonical_component"
  ),
  "tests.test_lane_component_selection_cli",
  "tests.test_lane_follow_verification",
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
