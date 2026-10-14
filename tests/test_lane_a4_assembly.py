"""Assembled contract coverage for independently completed Lane A units."""

import unittest

from tests import (
  test_consumer_terminal_lifecycle,
  test_retry_evidence,
  test_hosted_version_identity,
  test_phase_terminal,
  test_terminal_tag,
  test_on_demand_plan,
  test_publish_hosted_result,
  test_on_demand_workflow,
)


def load_tests(loader, standard_tests, pattern):
  combined = unittest.TestSuite()
  for module in (
    test_consumer_terminal_lifecycle,
    test_retry_evidence,
    test_hosted_version_identity,
    test_phase_terminal,
    test_terminal_tag,
    test_on_demand_plan,
    test_publish_hosted_result,
    test_on_demand_workflow,
  ):
    combined.addTests(loader.loadTestsFromModule(module))
  return combined


if __name__ == "__main__":
  unittest.main()
