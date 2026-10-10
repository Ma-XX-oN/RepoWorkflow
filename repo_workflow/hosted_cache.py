"""Provider-verified hosted GREEN/temporary cache from preceding publication.

This is separate from the local-only cache.  A JSONL claim is never authority:
each eligible hosted record must bind to a completed, successful GitHub
workflow run with the exact invocation, branch, and candidate identities.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import subprocess
from urllib.request import Request, urlopen


def _git(root: Path, *args: str) -> str:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )
  if result.returncode:
    raise ValueError("cannot verify prior hosted publication")
  return result.stdout.strip()


def _provider_run(repo: str, run_id: int, token: str) -> dict:
  if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
    raise ValueError("invalid GitHub repository identity")
  request = Request(
    f"https://api.github.com/repos/{repo}/actions/runs/{run_id}",
    headers={
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  )
  with urlopen(request, timeout=12) as response:
    return json.load(response)


def verified_hosted_passes(
  root: Path, *, stage: str, revision: str, fingerprint: str,
  invocation: str, branch: str, repository: str, token: str,
  provider_lookup=None,
) -> set[str]:
  """Read previous remote publication without changing the tested checkout.

  Network and malformed evidence failures are cache MISS, never PASS.
  """
  if (
    stage not in {"GREEN", "temporary"}
    or not re.fullmatch(r"[0-9a-f]{40}", revision)
    or not re.fullmatch(r"[0-9a-f]{40}", invocation)
    or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    or not re.fullmatch(r"issue-([1-9][0-9]*)(?:-.*)?", branch)
    or not token or not repository
  ):
    return set()
  issue = re.match(r"issue-([1-9][0-9]*)", branch).group(1)
  relative = f".repoworkflow/validation/testResults-{issue}.jsonl"
  lookup = provider_lookup or _provider_run
  try:
    if _git(root, "rev-parse", invocation + "^") == revision:
      # First invocation has no earlier hosted publication.
      return set()
    prior = _git(root, "rev-parse", invocation + "^")
    if not _git(root, "show", "-s", "--format=%s", prior).startswith(
      "test: publish hosted evidence from run "
    ):
      return set()
    if _git(root, "diff-tree", "--no-commit-id", "--name-only",
            "-r", prior).splitlines() != [relative]:
      return set()
    previous = _git(root, "show", prior + ":" + relative)
    if not previous:
      return set()
    latest: dict[str, bool] = {}
    for line in previous.splitlines():
      record = json.loads(line)
      if not isinstance(record, dict):
        return set()
      if (
        record.get("kind") != stage
        or record.get("testSHA") != revision
        or record.get("catalogueSHA256") != fingerprint
      ):
        continue
      run_id = record.get("providerRunId")
      invoked = record.get("providerInvocationSHA")
      if (
        record.get("runner") != "github-actions"
        or type(run_id) is not int or run_id < 1
        or not isinstance(invoked, str)
        or not re.fullmatch(r"[0-9a-f]{40}", invoked)
        or record.get("providerCandidateSHA") != revision
        or record.get("providerStage") !=
          ("GREEN-testing" if stage == "GREEN" else "temp-testing")
        or record.get("branch") != branch
      ):
        return set()
      provider = lookup(repository, run_id, token)
      if (
        provider.get("id") != run_id
        or provider.get("status") != "completed"
        or provider.get("conclusion") != "success"
        or provider.get("head_sha") != invoked
        or provider.get("head_branch") != branch
        or provider.get("event") != "push"
        or ".github/workflows/on-demand-ci.yml" not in
          str(provider.get("path", ""))
      ):
        return set()
      valid = (
        record.get("result") == "succeeded"
        and record.get("reusable") is True
        and record.get("headChangedDuringTest") is False
        and record.get("uncommittedChanges") == []
        and record.get("platform") == {
          "os": platform.system(), "architecture": platform.machine(),
          "runtime": platform.python_version(),
        }
      )
      groups = record.get("groups")
      if not isinstance(groups, list) or not groups:
        return set()
      seen: set[str] = set()
      for group in groups:
        if (
          not isinstance(group, dict)
          or not isinstance(group.get("group"), str)
          or not group["group"] or group["group"] in seen
        ):
          return set()
        seen.add(group["group"])
        latest[group["group"]] = (
          valid and type(group.get("exit_code")) is int
          and group["exit_code"] == 0
        )
    return {group for group, valid in latest.items() if valid}
  except (OSError, ValueError, TypeError, KeyError, RuntimeError):
    return set()
