import unittest
from unittest.mock import patch

from repo_workflow.terminal_style import (
  TerminalStyleError,
  TerminalStyler,
)


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

  def test_always_mode_fails_if_supported_backend_is_missing(self):
    with patch("repo_workflow.terminal_style.Console", None):
      with self.assertRaisesRegex(
        TerminalStyleError,
        "python -m pip install -r requirements.txt",
      ):
        TerminalStyler("always")

  def test_auto_mode_remains_plain_if_backend_is_missing(self):
    with patch("repo_workflow.terminal_style.Console", None):
      styler = TerminalStyler("auto")
    self.assertEqual(styler.lane_colour("A")("node"), "node")

  def test_invalid_mode_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "auto, always, or never"):
      TerminalStyler("sometimes")


if __name__ == "__main__":
  unittest.main()
