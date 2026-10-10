import unittest


class ExpectedRed(unittest.TestCase):
  def test_declared_failure(self):
    self.assertEqual(1, 1, "issue-541-provider-behavioural-failure")
