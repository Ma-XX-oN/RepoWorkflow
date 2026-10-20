#!/usr/bin/env python3
"""Authenticated, read-only #681 destination snapshot acceptance on GitHub."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))

from repo_host_github_integration_destination import (
  read_destination_snapshot,
)
from repo_host_github_provider import GitHubBackend


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def main():
  repository = os.environ["GITHUB_REPOSITORY"]
  expected = os.environ["EXPECTED_SOURCE_SHA"]
  if (_SHA.fullmatch(expected) is None
      or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
      ).strip() != expected):
    raise RuntimeError("hosted integration v2 source identity changed")
  backend = GitHubBackend(repository)
  snapshot = read_destination_snapshot(backend, "main")
  if (snapshot["ref"] != "refs/heads/main"
      or _SHA.fullmatch(snapshot["sha"]) is None
      or snapshot["policy_present"] == (snapshot["policy_text"] is None)):
    raise RuntimeError("provider destination snapshot malformed")
  print(json.dumps({
    "repository": repository, "source_sha": expected,
    "destination": snapshot["destination"],
    "destination_sha": snapshot["sha"],
    "policy_present": snapshot["policy_present"],
    "policy_length": (len(snapshot["policy_text"])
                      if snapshot["policy_present"] else None),
    "result": "PASS",
  }, sort_keys=True))


if __name__ == "__main__":
  main()
