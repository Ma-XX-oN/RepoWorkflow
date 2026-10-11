"""Verify candidate-bound hosted evidence against GitHub Actions provider facts.

The API is read-only. Missing/inaccessible/partial provider data fails closed.
This does not replace atomic server-side merge protections.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_SHA = re.compile(r"[0-9a-f]{40}")


def github_json(endpoint: str) -> dict:
  if not endpoint.startswith("https://api.github.com/repos/"):
    raise ValueError("unexpected provider API origin")
  headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "RepoWorkflow-evidence-check",
  }
  token = os.getenv("GITHUB_TOKEN")
  if token:
    headers["Authorization"] = "Bearer " + token
  try:
    with urlopen(Request(endpoint, headers=headers), timeout=12) as response:
      value = json.load(response)
  except (HTTPError, URLError, TimeoutError, ValueError) as error:
    raise ValueError("GitHub provider evidence unavailable") from error
  if not isinstance(value, dict):
    raise ValueError("GitHub provider returned invalid evidence")
  return value


def _verified_candidate_lineage(
  read: Callable[[str], dict], base: str,
  parent: str, candidate: str,
) -> bool:
  """Authenticate immutable publication/retry commits back to original source."""
  seen: set[str] = set()
  for _ in range(64):
    if parent == candidate:
      return True
    if _SHA.fullmatch(parent) is None or parent in seen:
      return False
    seen.add(parent)
    commit = read(base + "/commits/" + parent)
    if not isinstance(commit, dict):
      return False
    parents = commit.get("parents")
    files = commit.get("files")
    if (not isinstance(parents, list) or len(parents) != 1
        or not isinstance(parents[0], dict)
        or not isinstance(files, list) or len(files) != 1
        or not isinstance(files[0], dict)):
      return False
    previous = parents[0].get("sha")
    changed = files[0].get("filename")
    if not isinstance(previous, str) or _SHA.fullmatch(previous) is None:
      return False
    if changed == ".ci/run":
      marker = read(base + "/contents/.ci/run?ref=" + parent)
      stage_marker = _decode_marker(marker)
      if stage_marker is None or not stage_marker.endswith(" " + previous + "\n"):
        return False
      if stage_marker.split(" ", 1)[0] not in {
        "RED-testing", "GREEN-testing", "temp-testing",
        "regression-testing", "integration-testing",
      }:
        return False
    elif re.fullmatch(
      r"[.]repoworkflow/validation/testResults-[1-9][0-9]*[.]jsonl",
      str(changed),
    ):
      message = commit.get("commit", {}).get("message", "")
      if not isinstance(message, str) or not message.startswith(
        "test: publish hosted evidence from run "
      ):
        return False
    else:
      return False
    parent = previous
  return False


def _decode_marker(marker: dict) -> str | None:
  if (not isinstance(marker, dict) or marker.get("encoding") != "base64"
      or not isinstance(marker.get("content"), str)):
    return None
  try:
    raw = marker["content"].replace("\n", "").replace("\r", "")
    return base64.b64decode(raw, validate=True).decode("utf-8")
  except (ValueError, UnicodeError):
    return None


def verify_hosted_stage(
  record: dict, *, repo: str, stage: str,
  read: Callable[[str], dict] = github_json,
) -> bool:
  if stage not in {
    "RED-testing", "temp-testing", "GREEN-testing",
    "regression-testing", "integration-testing",
  }:
    return False
  if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is None:
    return False
  run_id = record.get("providerRunId")
  invocation = record.get("providerInvocationSHA")
  candidate = record.get("providerCandidateSHA")
  if (
    type(run_id) is not int or run_id <= 0
    or not isinstance(invocation, str)
    or _SHA.fullmatch(invocation) is None
    or not isinstance(candidate, str) or _SHA.fullmatch(candidate) is None
    or record.get("providerStage") != stage
  ):
    return False
  base = "https://api.github.com/repos/" + repo
  try:
    run = read(base + "/actions/runs/" + str(run_id))
    commit = read(base + "/git/commits/" + invocation)
    marker = read(base + "/contents/.ci/run?ref=" + invocation)
    jobs_page = read(
      base + "/actions/runs/" + str(run_id) + "/jobs?per_page=100"
    )
  except (ValueError, KeyError, TypeError):
    return False
  if not all(isinstance(item, dict) for item in (run, commit, marker, jobs_page)):
    return False
  if (
    run.get("id") != run_id
    or run.get("conclusion") != "success"
    or run.get("status") != "completed"
    or run.get("event") != "push"
    or run.get("name") != "RepoWorkflow On-Demand CI (candidate)"
    or run.get("head_sha") != invocation
    or not isinstance(commit.get("parents"), list)
    or len(commit["parents"]) != 1
    or not isinstance(commit["parents"][0], dict)
  ):
    return False
  request_text = _decode_marker(marker)
  parent = commit["parents"][0].get("sha")
  if (not isinstance(parent, str) or request_text != stage + " " + parent + "\n"):
    return False
  try:
    if not _verified_candidate_lineage(read, base, parent, candidate):
      return False
  except (ValueError, KeyError, TypeError):
    return False
  jobs = jobs_page.get("jobs")
  if not isinstance(jobs, list) or jobs_page.get("total_count") != len(jobs):
    return False
  actual = {}
  for job in jobs:
    if not isinstance(job, dict) or not isinstance(job.get("name"), str):
      return False
    if job["name"] in actual:
      return False
    actual[job["name"]] = job.get("conclusion")
  required = {"plan", "validate"}
  if stage == "integration-testing":
    for group in (
      "argv-limits", "graph-renderer-platform", "ticket-merge-platform",
    ):
      for system in ("ubuntu-latest", "windows-latest", "macos-latest"):
        required.add(group + " (" + system + ")")
  return all(actual.get(name) == "success" for name in required)


def verify_hosted_integration(
  record: dict, *, repo: str, read: Callable[[str], dict] = github_json,
) -> bool:
  return verify_hosted_stage(
    record, repo=repo, stage="integration-testing", read=read,
  )
