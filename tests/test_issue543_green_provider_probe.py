import unittest

class GreenProviderProbe(unittest.TestCase):
  def test_green_result(self):
    self.assertEqual(2 + 2, 4)
