#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from repo_workflow.ticket_merge import TicketMergeError, merge_files


def main() -> int:
  if len(sys.argv) != 4:
    print(
      "usage: merge-ticket-state.py BASE OURS THEIRS",
      file=sys.stderr,
    )
    return 2
  try:
    merge_files(
      Path.cwd(),
      Path(sys.argv[1]),
      Path(sys.argv[2]),
      Path(sys.argv[3]),
    )
  except TicketMergeError as error:
    print(f"RepoWorkflow ticket merge conflict: {error}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  # All Python output, including print() and tracebacks, uses one UTF-8 boundary.
  from pathlib import Path
  import sys
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  from repo_workflow.output import configure_utf8_output
  if not configure_utf8_output():
    raise SystemExit(2)
  raise SystemExit(main())
