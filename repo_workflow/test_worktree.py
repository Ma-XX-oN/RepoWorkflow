"""Track both source and destination of staged or unstaged Git renames."""
from pathlib import Path
import subprocess
from .test_results_reader import TestCommandError


def tracked_input_changes(root: Path, evidence_path: Path) -> list[str]:
  # The append-only evidence log does not count as a changed test input.
  status = subprocess.run(
    ["git", "-C", str(root), "status", "--porcelain", "-z",
     "--untracked-files=all"],
    capture_output=True, check=False,
  )
  if status.returncode:
    raise TestCommandError("cannot inspect working-tree changes")
  relative_evidence = evidence_path.relative_to(root).as_posix()
  entries = status.stdout.decode("utf-8", errors="surrogateescape").split("\0")
  changed: set[str] = set()
  index = 0
  while index < len(entries):
    entry = entries[index]
    index += 1
    if not entry:
      continue
    if len(entry) < 4 or entry[2] != " ":
      raise TestCommandError("malformed working-tree status")
    changed.add(entry[3:])
    if "R" in entry[:2] or "C" in entry[:2]:
      if index >= len(entries) or not entries[index]:
        raise TestCommandError("incomplete working-tree rename record")
      changed.add(entries[index])
      index += 1
  return sorted(changed - {relative_evidence})

