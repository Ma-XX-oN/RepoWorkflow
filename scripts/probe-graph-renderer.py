#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_workflow.graph_render import render_graph
from repo_workflow.graph_render_model import (
  AlignedColumn,
  FormatEntry,
  Graph,
  GraphSiblings,
  Lane,
)
from repo_workflow.terminal_style import TerminalStyler


def plain(text: str) -> str:
  return text


def formatter(entries: tuple[FormatEntry, ...]) -> AlignedColumn:
  styler = TerminalStyler("never")
  width = max(
    (styler.display_width(entry.raw_text) for entry in entries),
    default=0,
  )
  strings = tuple(
    entry.colour(
      entry.raw_text
      + " " * (width - styler.display_width(entry.raw_text))
    )
    for entry in entries
  )
  return AlignedColumn(strings, width)


def main() -> int:
  x = GraphSiblings(("X",))
  y = GraphSiblings(("Y",))
  p = GraphSiblings(("P",))
  a = GraphSiblings(("A",), (x,))
  b = GraphSiblings(("B",), (x, y, p))
  c = GraphSiblings(("C",), (y,))
  x.to_nodes = (p,)
  y.to_nodes = (p,)

  graph = Graph(
    (a, b, c, x, y, p),
    (
      Lane(("A", "X", "P"), plain),
      Lane(("B",), plain),
      Lane(("C", "Y"), plain),
    ),
    plain,
    formatter,
  )
  first = render_graph(graph)
  second = render_graph(
    Graph(
      (p, y, x, c, b, a),
      tuple(reversed(graph.lanes)),
      plain,
      formatter,
    )
  )
  if first.lines != second.lines or first.routes != second.routes:
    raise SystemExit("graph renderer is not deterministic")

  rendered = "\n".join(first.lines)
  if not ("↑" in rendered or "↓" in rendered):
    raise SystemExit("directed vertical routing marker is missing")

  styler = TerminalStyler("never")
  if styler.display_width("e\u0301") != 1:
    raise SystemExit("combining-character width is incorrect")
  if styler.display_width("界") != 2:
    raise SystemExit("wide-character width is incorrect")

  print("graph renderer probe ok")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
