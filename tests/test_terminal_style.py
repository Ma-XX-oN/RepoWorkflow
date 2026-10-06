import unittest

from repo_workflow.terminal_style import TerminalStyler


class TerminalStyleTests(unittest.TestCase):
  def test_never_mode_is_plain(self):
    styler = TerminalStyler("never")
    self.assertEqual(styler.lane_colour("A")("node"), "node")
    self.assertEqual(styler.default_edge_colour()("─"), "─")

  def test_display_width_is_terminal_cell_oriented(self):
    styler = TerminalStyler("never")
    self.assertEqual(styler.display_width("ABC"), 3)
    self.assertEqual(styler.display_width("e\u0301"), 1)
    self.assertEqual(styler.display_width("界"), 2)

  def test_invalid_mode_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "auto, always, or never"):
      TerminalStyler("sometimes")


if __name__ == "__main__":
  unittest.main()
