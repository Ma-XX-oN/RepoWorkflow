import unittest

class RedProviderProbe(unittest.TestCase):
  def test_declared_failure(self):
    self.fail("issue543 declared red invariant 20261013")
