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
