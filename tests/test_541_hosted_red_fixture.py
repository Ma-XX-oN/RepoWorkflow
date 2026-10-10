import unittest


class HostedRedProbe(unittest.TestCase):
  def test_expected_invariant_failure(self):
    self.assertEqual(1, 1, "issue-541-disposable-hosted-expected-red")


if __name__ == "__main__":
  unittest.main()
