#!/usr/bin/env python3
"""Read-only hosted GitHub provider evidence for issue #97.

This runs the shipped Python GitHub backend against the real GitHub API.
It never exercises a mutation, verifier or reservation, and is NOT live
mutation acceptance.  GitHub credentials come only from the runner.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters"))

from repo_host_github_provider import GitHubBackend


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--repository", required=True)
  parser.add_argument("--issue", type=int, required=True)
  parser.add_argument("--pull", type=int, required=True)
  parser.add_argument("--branch", required=True)
  parser.add_argument("--expected-sha", required=True)
  args = parser.parse_args()

  if args.issue <= 0 or args.pull <= 0:
    parser.error("issue and PR numbers must be positive")
  if not args.branch or "/" not in args.repository:
    parser.error("repository and branch identities required")

  backend = GitHubBackend(args.repository)
  actor = backend.identity()
  if not isinstance(actor.get("login"), str) or not actor["login"]:
    raise RuntimeError("GitHub token principal could not be authenticated")
  issue = backend.issue(args.issue)
  pr = backend.pull(args.pull)
  remote = backend.get("git/ref/heads/" + args.branch)

  observed = remote["object"]["sha"]
  if remote["ref"] != "refs/heads/" + args.branch:
    raise RuntimeError("remote branch identity mismatch")
  if observed != args.expected_sha:
    raise RuntimeError("remote head changed since invoking workflow")
  if pr["head"]["sha"] != observed:
    raise RuntimeError("PR head does not match remote branch")
  if pr["head"]["ref"] != args.branch:
    raise RuntimeError("PR source branch mismatch")
  if pr["head"]["repo"]["full_name"] != args.repository:
    raise RuntimeError("PR source repository mismatch")

  print(json.dumps({
    "result": "PASS", "mode": "READ_ONLY",
    "repository": args.repository, "issue": issue["number"],
    "pull": pr["number"], "head_sha": observed,
    "mutation_authorization": "NOT_TESTED",
    "observed_actor": actor["login"],
    "mutation_side_effects": 0,
  }, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
