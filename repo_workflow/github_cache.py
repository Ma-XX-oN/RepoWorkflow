"""Recognise a GitHub-origin repository for read-only hosted cache verification."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Callable

from .github_evidence import verify_hosted_stage


def hosted_cache_checker(root: Path, stage: str) -> Callable[[dict], bool] | None:
  command = subprocess.run(
    ["git", "-C", str(root), "remote", "get-url", "origin"],
    text=True, capture_output=True, check=False,
  )
  if command.returncode:
    return None
  raw = command.stdout.strip()
  match = (
    re.fullmatch(
      r"https://github[.]com/([\w.-]+/[\w.-]+?)(?:[.]git)?", raw,
    )
    or re.fullmatch(
      r"git@github[.]com:([\w.-]+/[\w.-]+?)(?:[.]git)?", raw,
    )
  )
  if match is None:
    return None
  repo = match.group(1)
  provider_stage = {
    "GREEN": "GREEN-testing",
    "temporary": "temp-testing",
  }.get(stage)
  if provider_stage is None:
    return None
  return lambda record: verify_hosted_stage(
    record, repo=repo, stage=provider_stage,
  )


def read_remote_published_log(
  root: Path, *, branch: str, relative: str,
) -> str | None:
  """Read already published results without requesting another test cycle."""
  if re.fullmatch(r"issue-[1-9][0-9]*(?:-[A-Za-z0-9_.-]+)?", branch) is None:
    return None
  if re.fullmatch(
    r"[.]repoworkflow/validation/testResults-[1-9][0-9]*[.]jsonl",
    relative,
  ) is None:
    return None
  fetched = subprocess.run(
    ["git", "-C", str(root), "fetch", "--no-tags", "origin",
     "refs/heads/" + branch],
    text=True, capture_output=True, check=False,
  )
  if fetched.returncode:
    return None
  showed = subprocess.run(
    ["git", "-C", str(root), "show", "FETCH_HEAD:" + relative],
    text=True, capture_output=True, check=False,
  )
  return showed.stdout if showed.returncode == 0 else None
