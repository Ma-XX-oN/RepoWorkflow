"""Intentional RED provider fixture, excluded from test_*.py discovery."""
import unittest


class ExpectedRedFixture(unittest.TestCase):
  def test_failure(self):
    self.fail("ISSUE543_FINAL_EXPECTED_RED")


if __name__ == "__main__":
  unittest.main()
