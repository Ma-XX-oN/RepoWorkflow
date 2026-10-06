from __future__ import annotations

from collections.abc import Callable
from io import StringIO
import sys
import unicodedata


try:
  from rich.cells import cell_len as _rich_cell_len
  from rich.console import Console
  from rich.text import Text
except ImportError:  # Optional enhancement; plain rendering remains available.
  Console = None
  Text = None
  _rich_cell_len = None


ColourFunction = Callable[[str], str]


_PALETTE = (
  "red",
  "green",
  "yellow",
  "blue",
  "magenta",
  "cyan",
  "bright_red",
  "bright_green",
  "bright_yellow",
  "bright_blue",
  "bright_magenta",
  "bright_cyan",
)


class TerminalStyleError(ValueError):
  pass


class TerminalStyler:
  def __init__(self, mode: str, *, stream=None):
    if mode not in {"auto", "always", "never"}:
      raise TerminalStyleError(
        "terminal colour mode must be auto, always, or never"
      )
    if mode == "always" and Console is None:
      raise TerminalStyleError(
        "terminal colour backend is unavailable; install RepoWorkflow "
        "runtime dependencies with: python -m pip install -r "
        "requirements.txt"
      )
    self.mode = mode
    self.stream = sys.stdout if stream is None else stream
    self._console = self._make_console()

  @property
  def styling_available(self) -> bool:
    return self._console is not None and self._console.color_system is not None

  def display_width(self, text: str) -> int:
    if _rich_cell_len is not None:
      return _rich_cell_len(text)
    return _fallback_cell_width(text)

  def lane_colour(self, lane_name: str) -> ColourFunction:
    index = _lane_index(lane_name) % len(_PALETTE)
    return self._style(_PALETTE[index])

  def default_edge_colour(self) -> ColourFunction:
    return self._style("bright_black")

  def _make_console(self):
    if self.mode == "never" or Console is None:
      return None
    force_terminal = True if self.mode == "always" else None
    return Console(
      file=self.stream,
      force_terminal=force_terminal,
      color_system="auto",
      soft_wrap=True,
    )

  def _style(self, style: str) -> ColourFunction:
    if not self.styling_available:
      return _identity

    def apply(text: str) -> str:
      if not text:
        return text
      with self._console.capture() as capture:
        self._console.print(
          Text(text, style=style),
          end="",
          soft_wrap=True,
        )
      return capture.get()

    return apply


def _identity(text: str) -> str:
  return text


def _fallback_cell_width(text: str) -> int:
  width = 0
  for char in text:
    if unicodedata.combining(char):
      continue
    if unicodedata.category(char) in {"Cf", "Cc"}:
      continue
    width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
  return width


def _lane_index(value: str) -> int:
  result = 0
  for char in value:
    if not ("A" <= char <= "Z"):
      raise ValueError(f"invalid lane name: {value!r}")
    result = result * 26 + ord(char) - ord("A") + 1
  return result - 1
