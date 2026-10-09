"""Isolated hosted RED negative probe; never merge into production."""
import unittest


class RedFailureProbe(unittest.TestCase):
  def test_expected_assertion_failure(self):
    raise RuntimeError("intentional RED infrastructure/error fixture")
