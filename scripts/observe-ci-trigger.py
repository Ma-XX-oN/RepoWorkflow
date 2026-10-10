"""Read-only GitHub Actions observation for #628; never dispatch a workflow."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ObservationError(RuntimeError):
  pass


def utc(value):
  result = datetime.fromisoformat(value.replace("Z", "+00:00"))
  if result.tzinfo is None:
    raise ObservationError("observation times must include an offset")
  return result.astimezone(timezone.utc)


def github_get(path, token):
  req = Request(
    "https://api.github.com" + path,
    headers={
      "Accept": "application/vnd.github+json",
      "Authorization": "Bearer " + token,
      "X-GitHub-Api-Version": "2022-11-28",
    },
  )
  try:
    with urlopen(req, timeout=30) as response:
      return json.load(response)
  except (HTTPError, OSError, ValueError) as error:
    raise ObservationError(f"GitHub provider request failed for {path}: {error}") from error


def all_pages(path, collection, token, fetch=github_get):
  results = []
  for page in range(1, 101):
    separator = "&" if "?" in path else "?"
    item = fetch(f"{path}{separator}per_page=100&page={page}", token)
    if collection not in item or not isinstance(item[collection], list):
      raise ObservationError("provider response missing " + collection)
    batch = item[collection]
    results.extend(batch)
    if len(batch) < 100:
      return results
  raise ObservationError("provider pagination not exhausted")



ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repo_workflow.ci_invocation import CiInvocationError, parse_invocation


def original_candidate_provider(root, starting_sha, token, fetch=github_get):
  """Walk an exact verified marker-only retry chain to its source candidate."""
  sha = starting_sha
  seen = set()
  for _ in range(1000):
    if sha in seen:
      raise ObservationError("cycle in provider invocation ancestry")
    seen.add(sha)
    commit = fetch(root + "/commits/" + sha, token)
    files = [item.get("filename") for item in commit.get("files", [])]
    parents = commit.get("parents", [])
    if len(parents) != 1:
      return sha
    parent = parents[0].get("sha")
    if files == [".ci/run"]:
      marker_response = fetch(
        root + "/contents/.ci/run?ref=" + quote(sha, safe=""), token,
      )
      if marker_response.get("encoding") != "base64":
        raise ObservationError("retry marker is not base64 content")
      try:
        text = base64.b64decode(
          marker_response["content"], validate=False,
        ).decode("utf-8")
        request = parse_invocation(text)
      except (KeyError, ValueError, UnicodeError, CiInvocationError) as error:
        raise ObservationError("malformed retry marker") from error
      if request.previous_tip != parent:
        raise ObservationError("retry marker parent SHA mismatch")
    elif (
      len(files) == 1
      and re.fullmatch(
        r"\\.repoworkflow/validation/testResults-[1-9][0-9]*\\.jsonl",
        files[0],
      )
      and commit.get("commit", {}).get("message", "").split("\n", 1)[0].startswith(
        "test: publish hosted evidence from run "
      )
    ):
      pass
    else:
      return sha
    sha = parent
  raise ObservationError("retry chain depth exceeded")


def verify_provider_request(root, sha, token, fetch=github_get):
  """Independently bind provider invocation SHA to its committed parent."""
  commit = fetch(root + "/commits/" + sha, token)
  parents = commit.get("parents", [])
  files = commit.get("files", [])
  if len(parents) != 1 or [f.get("filename") for f in files] != [".ci/run"]:
    raise ObservationError("provider commit is not a dedicated single-parent request")
  contents = fetch(
    root + "/contents/.ci/run?ref=" + quote(sha, safe=""), token,
  )
  if contents.get("encoding") != "base64":
    raise ObservationError("provider marker is not base64 content")
  try:
    marker = base64.b64decode(contents["content"], validate=False).decode("utf-8")
    request = parse_invocation(marker)
  except (KeyError, ValueError, UnicodeError, CiInvocationError) as error:
    raise ObservationError("invalid committed provider marker") from error
  if request.previous_tip != parents[0].get("sha"):
    raise ObservationError("provider candidate SHA does not match request parent")
  tested_sha = original_candidate_provider(
    root, request.previous_tip, token, fetch,
  )
  return {
    "stage": request.stage, "previous_tip": request.previous_tip,
    "tested_sha": tested_sha, "invocation_sha": sha,
  }

def observe(repo, workflow, branch, start, end, token, fetch=github_get):
  if utc(start) > utc(end):
    raise ObservationError("observation window reversed")
  root = "/repos/" + quote(repo, safe="/") + "/actions"
  workflow_path = root + "/workflows/" + quote(workflow, safe="")
  descriptor = fetch(workflow_path, token)
  if descriptor.get("state") != "active":
    raise ObservationError("workflow is not active: no zero-job assertion permitted")
  observed_at = datetime.now(timezone.utc)
  if observed_at < utc(end):
    raise ObservationError("observation window has not ended")
  runs = all_pages(
    workflow_path + "/runs?branch=" + quote(branch, safe=""),
    "workflow_runs", token, fetch,
  )
  selected = []
  seen_invocations = set()
  for run in runs:
    created = utc(run["created_at"])
    if not utc(start) <= created <= utc(end):
      continue
    if run.get("head_branch") != branch or run.get("event") != "push":
      raise ObservationError("provider returned mismatched branch/event")
    if run.get("status") != "completed" or not run.get("conclusion"):
      raise ObservationError("run still pending; cannot certify final count")
    if run["head_sha"] in seen_invocations:
      raise ObservationError("duplicate hosted run for one invocation SHA")
    seen_invocations.add(run["head_sha"])
    invocation = verify_provider_request(
      "/repos/" + quote(repo, safe="/"), run["head_sha"], token, fetch,
    )
    jobs = all_pages(
      root + "/runs/" + str(run["id"]) + "/jobs",
      "jobs", token, fetch,
    )
    selected.append({
      "run_id": run["id"],
      "run_url": run["html_url"],
      "invocation_sha": invocation["invocation_sha"],
      "previous_tip": invocation["previous_tip"],
      "tested_sha": invocation["tested_sha"],
      "stage": invocation["stage"],
      "conclusion": run.get("conclusion"),
      "job_count": len(jobs),
      "executed_test_job_count": sum(
        job.get("conclusion") != "skipped"
        and job.get("name", "").split(" (", 1)[0]
        in {"validate", "argv-limits", "graph-renderer-platform",
            "ticket-merge-platform"}
        for job in jobs
      ),
      "jobs": [{
        "id": job["id"],
        "name": job["name"],
        "conclusion": job.get("conclusion"),
      } for job in jobs],
    })
  return {
    "repo": repo,
    "workflow_id": descriptor["id"],
    "workflow_state": descriptor["state"],
    "branch": branch,
    "start": start,
    "end": end,
    "observed_at": observed_at.isoformat(),
    "run_count": len(selected),
    "job_count": sum(item["job_count"] for item in selected),
    "executed_test_job_count": sum(
      item["executed_test_job_count"] for item in selected
    ),
    "runs": selected,
  }


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True)
  parser.add_argument("--workflow", default="on-demand-ci.yml")
  parser.add_argument("--branch", required=True)
  parser.add_argument("--start", required=True)
  parser.add_argument("--end", required=True)
  parser.add_argument("--expected-test-jobs", type=int)
  parser.add_argument("--expected-runs", type=int)
  args = parser.parse_args()
  token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
  if not token:
    parser.error("GH_TOKEN or GITHUB_TOKEN required (read-only actions access)")
  try:
    result = observe(
      args.repo, args.workflow, args.branch, args.start, args.end, token,
    )
  except ObservationError as error:
    parser.exit(2, str(error) + "\n")
  print(json.dumps(result, indent=2, sort_keys=True))
  if args.expected_test_jobs is not None and (
    result["executed_test_job_count"] != args.expected_test_jobs
  ):
    parser.exit(1, "hosted test-job count did not match expectation\n")
  if args.expected_runs is not None and (
    result["run_count"] != args.expected_runs
  ):
    parser.exit(1, "hosted run count did not match expectation\n")


if __name__ == "__main__":
  main()
