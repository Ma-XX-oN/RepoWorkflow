#!/usr/bin/env python3
"""Probe read-only CI token's issue, PR and Git ref write permissions.

Every request omits mandatory provider fields.  GitHub cannot apply a
mutation from any of these requests, regardless of token privilege.
An authorization failure is recorded separately from validation failure.
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
  results = {}
  for operation, path in (
    ("issue.create", "issues"),
    ("pull_request.create", "pulls"),
    ("git_ref.create", "git/refs"),
  ):
    try:
      # Missing mandatory fields prevent provider-side mutation.
      backend.post(path, {})
    except ProviderError as exc:
      if exc.code not in {"unauthorized", "not_found", "conflict"}:
        raise RuntimeError(
          "unexpected error for " + operation + ": " + exc.code
        ) from exc
      results[operation] = {
        "permission": (
          "DENIED" if exc.code == "unauthorized" else "UNVERIFIED"
        ),
        "error": exc.code, "no_persisted_mutation": True,
      }
      continue
    raise RuntimeError(
      operation + " accepted an invalid empty mutation request"
    )
  print(json.dumps(results, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
