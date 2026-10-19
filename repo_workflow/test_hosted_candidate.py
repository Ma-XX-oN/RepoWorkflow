"""Pin on-demand tests to the already-approved exact source commit.

The runner's prepared source is an immutable test input. A local version
preparation commit would change the tested SHA before the hosted verifier runs.
"""
import os
from pathlib import Path
import re

from .git import current_branch, head_sha
from .test_results_reader import TestCommandError


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def hosted_candidate_bound(root: Path) -> bool:
  """True only for exact GitHub-hosted test source, never an unbound local test."""
  expected = os.environ.get("RWF_HOSTED_TEST_CANDIDATE")
  if expected is None:
    return (os.environ.get("GITHUB_ACTIONS") == "true"
      and os.environ.get("GITHUB_WORKFLOW") == "RepoWorkflow On-Demand CI"
      and os.environ.get("GITHUB_REF_NAME") == current_branch(root))
  if (os.environ.get("GITHUB_ACTIONS") != "true"
      or type(expected) is not str or _SHA.fullmatch(expected) is None
      or head_sha(root) != expected
      or os.environ.get("GITHUB_REF_NAME") != current_branch(root)):
    raise TestCommandError("hosted test candidate identity changed")
  return True

def publish_if_local(root: Path, *, stage: str) -> None:
  """Hosted result tags belong to the separate authenticated publisher."""
  if not hosted_candidate_bound(root):
    from .local_terminal import publish_local_terminal
    publish_local_terminal(root, stage=stage)

