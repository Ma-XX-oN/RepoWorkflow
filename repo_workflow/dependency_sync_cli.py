from __future__ import annotations
import json
from pathlib import Path
from .config import load_config
from .current_work_store import CurrentWorkStore
from .dependency_comparison import compare_dependencies
from .dependency_sync import sync_from_tickets, sync_to_tickets
from .issue_metadata import refresh_issue_metadata
from .relationship_store import RelationshipStore
from .runtime_identity import runtime_writer_identity
from .ticket_dependency_adapter import read_ticket_dependencies

def _target(root: Path) -> int:
  selected = CurrentWorkStore(root).read().value.selected_issue
  if selected is None:
    raise ValueError("dependency synchronization requires one selected issue in current-work state")
  return int(selected)

def _comparison(root: Path, config: dict, issue: int, direction: str):
  rwf = tuple(int(v) for v in RelationshipStore(root).direct_dependencies(issue))
  ticket = read_ticket_dependencies(root, config, issue)
  return compare_dependencies(rwf, ticket) if direction == "to-tickets" else compare_dependencies(ticket, rwf)

def dependency_sync_command(root: Path, words: tuple[str, ...]) -> int:
  if len(words) not in {2, 3} or words[0] != "dependency":
    raise ValueError("invalid dependency synchronization command")
  direction = words[1]
  if direction not in {"to-tickets", "from-tickets"}:
    raise ValueError("invalid dependency synchronization direction")
  option = None if len(words) == 2 else words[2]
  if option not in {None, "--compare", "--replace"}:
    raise ValueError("invalid dependency synchronization option")
  issue = _target(root)
  config = load_config(root)
  if option == "--compare":
    c = _comparison(root, config, issue, direction)
    print(json.dumps({"issue":issue,"direction":direction,"status":c.status.value,"source":list(c.source),"destination":list(c.destination),"additions":list(c.additions),"removals":list(c.removals)}, separators=(",", ":")))
    return 0
  writer = runtime_writer_identity()
  result = sync_to_tickets(root, config, issue, replace=option == "--replace") if direction == "to-tickets" else sync_from_tickets(root, config, issue, writer, replace=option == "--replace")
  if result.status.value == "SYNCHRONIZED":
    refresh_issue_metadata(root, config, writer)
  print(json.dumps({"issue":issue,"direction":direction,"status":result.status.value,"dependencies":list(result.dependencies)}, separators=(",", ":")))
  return 0
