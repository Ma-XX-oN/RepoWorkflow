#!/usr/bin/env python3
"""GitHub CI-status extension of the configured repo-info command.

The legacy repo-info GitHub owner retains its executable. This extension
delegates existing operations unchanged and owns only hosted CI API access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote


def fail(message: str) -> None:
  print(message, file=sys.stderr)
  raise SystemExit(2)


def gh_json(url: str) -> dict:
  try:
    result = subprocess.run(
      ["gh", "api", "--method", "GET", url],
      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout = result.stdout.decode("utf-8", "strict")
    stderr = result.stderr.decode("utf-8", "strict")
  except (OSError, UnicodeError) as exc:
    fail(f"GitHub CI invocation lookup failed: {exc}")
  if result.returncode:
    fail("GitHub CI invocation lookup failed: " + (stderr or stdout).strip())
  try:
    value = json.loads(stdout)
  except (ValueError, TypeError) as exc:
    fail(f"GitHub CI invocation response is malformed: {exc}")
  if not isinstance(value, dict):
    fail("GitHub CI invocation response must be an object")
  return value


def status(repository: str, workflow: str, branch: str, revision: str, attempt: int) -> None:
  if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
    fail("invalid GitHub repository identity")
  if not workflow or workflow.startswith("-") or "/" in workflow or "\\\\" in workflow:
    fail("invalid configured GitHub workflow identity")
  if re.fullmatch(r"CMD-[1-9][0-9]*-[^\\s\\x00-\\x1f]+", branch) is None:
    fail("invalid CMD branch")
  if re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None or attempt < 0:
    fail("invalid CI request identity")
  revision = revision.lower()
  matched: dict[int, dict] = {}
  # GitHub Actions returns at most 100 runs per page. Never turn an
  # incompletely enumerated provider result into 'not-observed'.
  for page in range(1, 101):
    endpoint = (
      f"repos/{repository}/actions/workflows/{quote(workflow, safe='')}/runs"
      f"?branch={quote(branch, safe='')}&head_sha={revision}"
      f"&event=push&per_page=100&page={page}"
    )
    data = gh_json(endpoint)
    runs = data.get("workflow_runs")
    if not isinstance(runs, list):
      fail("GitHub CI invocation response lacks workflow_runs")
    for run in runs:
      if not isinstance(run, dict):
        fail("GitHub CI invocation run is malformed")
      if (run.get("head_sha") != revision or
          run.get("head_branch") != branch or run.get("event") != "push"):
        continue
      run_id = run.get("id")
      if type(run_id) is not int or run_id <= 0:
        fail("GitHub CI invocation run ID is malformed")
      matched[run_id] = run
    if len(runs) < 100:
      break
  else:
    fail("GitHub CI invocation pagination limit reached; status unverified")

  state = "not-observed"
  run_id = None
  detail = None
  if len(matched) > 1:
    state = "unknown"
    detail = "multiple runs for the exact request revision"
  elif matched:
    run_id, run = next(iter(matched.items()))
    observed = run.get("status")
    if observed in {"queued", "requested", "waiting", "pending"}:
      state = "queued"
    elif observed == "in_progress":
      state = "running"
    elif observed == "completed":
      state = "completed"
    else:
      state = "unknown"
      detail = "unrecognized GitHub run status"
  print(json.dumps({
    "schema_version": 1,
    "branch": branch,
    "request_revision": revision,
    "attempt": attempt,
    "state": state,
    "run_id": run_id,
    "detail": detail,
  }, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str]) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--repository", required=True)
  parser.add_argument("--workflow")
  known, words = parser.parse_known_args(argv)
  if len(words) == 6 and words[:3] == ["ci", "invocation", "status"]:
    if not known.workflow:
      fail("GitHub CI invocation status requires --workflow WORKFLOW_FILE")
    try:
      attempt = int(words[5])
    except ValueError:
      fail("CI retry attempt must be nonnegative")
    status(known.repository, known.workflow, words[3], words[4], attempt)
    return 0
  # Preserve the current default provider's existing repository/issue behavior.
  if known.workflow is None or known.workflow:
    original = Path(__file__).with_name("repo-info-github.py")
    return subprocess.call([
      sys.executable, str(original), "--repository", known.repository, *words,
    ])
  return 2


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
