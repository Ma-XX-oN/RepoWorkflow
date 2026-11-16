"""Resolve test ownership independently of the checkout branch's spelling."""
from pathlib import Path
import re

from .git import current_branch
from .test_results_reader import TestCommandError


def testing_issue(root: Path, *, branch: str | None = None) -> int:
  """Resolve an issue from its branch, qualified PRELIM or development version.

  Parameters
  ----------
  root : Path
      Repository being tested.
  branch : str, optional
      Already observed branch name.

  Returns
  -------
  int
      Positive issue number. Unknown ownership raises TestCommandError;
      tests need an issue identity, but need not run on an issue branch.
  """
  branch = current_branch(root) if branch is None else branch
  if branch.startswith("PRELIM-"):
    from .prelim_queue import parse_ready_prelim
    submission = parse_ready_prelim("refs/heads/" + branch, "0" * 40)
    return int(submission.umbrella.removeprefix("issue-"))
  match = re.fullmatch(r"(?:PRELIM-)?issue-([1-9][0-9]*)(?:[-/].*)?", branch)
  if match:
    return int(match.group(1))
  if (root / ".ci/engine-version").is_file():
    from .engine_version_adapter import read_engine_version
    version = read_engine_version(root)
  elif (root / ".ci/repoworkflow.json").is_file():
    from .config import load_config
    from .version_adapter import read_development_version
    version = read_development_version(root, load_config(root))
  else:
    raise TestCommandError("testing requires an identifiable issue or development version")
  match = re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-issue\.([1-9][0-9]*)\.[0-9]+\.[0-9]+", version)
  if not match:
    raise TestCommandError("testing version does not identify an issue")
  return int(match.group(1))
