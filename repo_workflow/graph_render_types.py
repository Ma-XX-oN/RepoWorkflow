from __future__ import annotations

from dataclasses import dataclass

from .graph_render_model import ColourFunction, GraphSiblings, Lane


_L = 1
_R = 2
_U = 4
_D = 8


class GraphLayoutError(RuntimeError):
  pass


@dataclass(frozen=True)
class HiddenContinuation:
  semantic_source: str
  semantic_target: str
  column: int
  row: int


@dataclass(frozen=True)
class RouteRecord:
  source: str
  target: str
  kind: str
  hidden: tuple[HiddenContinuation, ...]

  def diagnostic(self) -> dict:
    return {
      "source": self.source,
      "target": self.target,
      "kind": self.kind,
      "hidden_columns": [item.column for item in self.hidden],
    }


@dataclass(frozen=True)
class SemanticEdge:
  source: str
  target: str
  source_group: GraphSiblings
  target_group: GraphSiblings
  lane: Lane | None
  colour: ColourFunction

  @property
  def key(self) -> tuple[str, str]:
    return self.source, self.target


@dataclass(frozen=True)
class Contribution:
  edge: SemanticEdge
  bits: int
  bundle: tuple[int, int] | None = None
  vertical_direction: int = 0


@dataclass(frozen=True)
class Placement:
  column: int
  row: int


@dataclass(frozen=True)
class Column:
  nodes: tuple[str, ...]
  formatted: tuple[str, ...]
  width: int


@dataclass(frozen=True)
class NodeToken:
  text: str
  width: int


@dataclass(frozen=True)
class LayoutPlan:
  width: int
  max_y: int
  node_tokens: dict[tuple[int, int], NodeToken]
  cells: dict[tuple[int, int], list[Contribution]]
  routes: tuple[RouteRecord, ...]
  default_colour: ColourFunction
