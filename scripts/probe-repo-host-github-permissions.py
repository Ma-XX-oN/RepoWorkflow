#!/usr/bin/env python3
"""Probe issue-create permission with a missing required title.

GitHub requires title for issue creation.  This invalid request cannot
create an issue, and distinguishes explicit permission rejection from
provider-side validation without granting write credentials to PR CI.
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
    backend.post("issues", {})
  except ProviderError as exc:
    if exc.code not in {"unauthorized", "not_found", "conflict"}:
      raise RuntimeError(
        "unexpected read-only token write outcome: " + exc.code
      ) from exc
    print(json.dumps({
      "result": (
        "PERMISSION_DENIED" if exc.code == "unauthorized"
        else "PERMISSION_UNVERIFIED"
      ),
      "error": exc.code,
      "target": "issue-create with missing required title",
      "no_persisted_mutation": True,
    }, sort_keys=True))
    return 0
  raise RuntimeError("read-only token unexpectedly accepted a write")


if __name__ == "__main__":
  raise SystemExit(main())
