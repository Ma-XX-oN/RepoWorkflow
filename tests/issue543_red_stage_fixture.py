"""Intentional hosted RED fixture; excluded from test_*.py discovery."""
import unittest


class ExpectedRedFixture(unittest.TestCase):
  def test_declared_behavioural_failure(self):
    self.fail("ISSUE543_EXPECTED_RED_CERT")


if __name__ == "__main__":
  unittest.main()
