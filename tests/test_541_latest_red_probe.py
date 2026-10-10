import unittest


class LatestHostedRed(unittest.TestCase):
  def test_declared_failure(self):
    self.assertEqual(2, 3, "issue-541-latest-provider-RED-behaviour")
