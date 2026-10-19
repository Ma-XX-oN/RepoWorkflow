"""Bind on-demand tests to a dedicated, exact-source invocation commit."""
import os
from pathlib import Path
import re
import subprocess

from .ci_invocation import parse_invocation
from .git import current_branch, head_sha
from .test_results_reader import TestCommandError


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _git(root, *args):
  result = subprocess.run(
    ["git", "-C", str(root), *args], capture_output=True, text=True,
    check=False,
  )
  if result.returncode:
    raise TestCommandError("hosted invocation object unavailable")
  return result.stdout.strip()


def hosted_candidate_bound(root: Path) -> bool:
  """Hosted stage is immutable only when its exact invocation was verified."""
  expected = os.environ.get("RWF_HOSTED_TEST_CANDIDATE")
  hosted = (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_WORKFLOW") == "RepoWorkflow On-Demand CI")
  if expected is None and not hosted:
    return False
  if (not hosted
      or os.environ.get("GITHUB_REF_NAME") != current_branch(root)):
    raise TestCommandError("hosted test candidate identity changed")
  candidate = head_sha(root)
  if expected is None:
    invocation = os.environ.get("GITHUB_SHA")
    if type(invocation) is not str or _SHA.fullmatch(invocation) is None:
      raise TestCommandError("hosted invocation identity absent")
    marker = parse_invocation(_git(root, "show", invocation + ":.ci/run") + "\n")
    ancestors = _git(root, "rev-list", "--parents", "-n", "1", invocation).split()
    changed = _git(root, "diff-tree", "--no-commit-id", "--name-only",
                   "-r", invocation).splitlines()
    if (len(ancestors) != 2 or ancestors[0] != invocation
        or marker.previous_tip != ancestors[1] or changed != [".ci/run"]):
      raise TestCommandError("hosted invocation is not an exact-source request")
    expected = marker.previous_tip
  if (type(expected) is not str or _SHA.fullmatch(expected) is None
      or candidate != expected):
    raise TestCommandError("hosted test candidate identity changed")
  return True


def publish_if_local(root: Path, *, stage: str) -> None:
  """The hosted result publisher owns terminal tags, not its test checkout."""
  if not hosted_candidate_bound(root):
    from .local_terminal import publish_local_terminal
    publish_local_terminal(root, stage=stage)
