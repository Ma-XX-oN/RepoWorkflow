import unittest


class ExpectedRed(unittest.TestCase):
  def test_declared_failure(self):
    self.assertEqual(1, 2, "issue-541-provider-behavioural-failure")
