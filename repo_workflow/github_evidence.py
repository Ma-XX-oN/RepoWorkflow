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


def verify_hosted_integration(
  record: dict, *, repo: str, read: Callable[[str], dict] = github_json,
) -> bool:
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
    or record.get("providerStage") != "integration-testing"
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
    or commit["parents"][0].get("sha") != candidate
    or marker.get("encoding") != "base64"
    or not isinstance(marker.get("content"), str)
  ):
    return False
  try:
    request = base64.b64decode(marker["content"], validate=False)
    request_text = request.decode("utf-8")
  except (ValueError, UnicodeError):
    return False
  if request_text != "integration-testing " + candidate + "\n":
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
  for group in ("argv-limits", "graph-renderer-platform", "ticket-merge-platform"):
    for system in ("ubuntu-latest", "windows-latest", "macos-latest"):
      required.add(group + " (" + system + ")")
  return all(actual.get(name) == "success" for name in required)
