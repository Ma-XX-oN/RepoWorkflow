#!/usr/bin/env python3
"""Probe a write transport request without affecting existing issues.

The target issue number is impossible within this repository.  This
probe never addresses an existing issue, pull request, branch or tag.
The call exercises GitHubBackend's actual transport and classification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))

from repo_host_github_provider import GitHubBackend, ProviderError


def main() -> int:
  backend = GitHubBackend("Ma-XX-oN/RepoWorkflow")
  try:
    backend.patch(
      "issues/2147483647",
      {"title": "NO EXISTING ISSUE MUST BE MUTATED"},
    )
  except ProviderError as exc:
    if exc.code not in {"unauthorized", "not_found"}:
      raise RuntimeError(
        "unexpected read-only token write outcome: " + exc.code
      ) from exc
    print(json.dumps({
      "result": (
        "PERMISSION_DENIED" if exc.code == "unauthorized"
        else "PERMISSION_UNVERIFIED"
      ),
      "error": exc.code,
      "target": "nonexistent issue 2147483647",
      "no_persisted_mutation": True,
    }, sort_keys=True))
    return 0
  raise RuntimeError("read-only token unexpectedly accepted a write")


if __name__ == "__main__":
  raise SystemExit(main())
