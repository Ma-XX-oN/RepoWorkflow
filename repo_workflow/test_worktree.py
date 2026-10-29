"""Track both source and destination of staged or unstaged Git renames."""
from pathlib import Path
from .git import GitError, git_bytes, git_wire_path
from .test_results_reader import TestCommandError


def tracked_input_changes(root: Path, evidence_path: Path) -> list[str]:
  # Git porcelain -z is an opaque byte protocol, not host-locale text.
  try:
    raw = git_bytes(root, "status", "--porcelain=v1", "-z",
                    "--untracked-files=all").stdout
    if raw and not raw.endswith(b"\0"):
      raise TestCommandError("unterminated working-tree status")
    parts = raw.split(b"\0") if raw else []
    changed: set[str] = set()
    index = 0
    while index < len(parts) - 1:
      entry = parts[index]
      if len(entry) < 4 or entry[2:3] != b" " or entry[:2] == b"  ":
        raise TestCommandError("malformed working-tree status")
      changed.add(git_wire_path(entry[3:]))
      if b"R" in entry[:2] or b"C" in entry[:2]:
        index += 1
        if index >= len(parts) - 1 or not parts[index]:
          raise TestCommandError("incomplete working-tree rename record")
        changed.add(git_wire_path(parts[index]))
      index += 1
  except GitError as error:
    raise TestCommandError("cannot inspect working-tree changes") from error
  relative_evidence = evidence_path.relative_to(root).as_posix()
  return sorted(changed - {relative_evidence})
