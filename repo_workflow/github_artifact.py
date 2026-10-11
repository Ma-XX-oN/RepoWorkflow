"""Authenticate canonical hosted evidence against immutable Actions artifacts.

A successful run/job does not authenticate user-writable JSONL group claims.
"""
from __future__ import annotations

from io import BytesIO
import json
import os
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
  HTTPRedirectHandler, Request, build_opener,
)
from zipfile import BadZipFile, ZipFile

from .github_evidence import github_json, verify_hosted_stage


_MAX_ARCHIVE = 8 * 1024 * 1024


class _StripCrossHostAuthorization(HTTPRedirectHandler):
  """Do not send the API bearer token to redirected signed artifact storage."""
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
    if (redirected is not None and
        urlsplit(req.full_url).netloc != urlsplit(newurl).netloc):
      redirected.remove_header("Authorization")
    return redirected


def _artifact_bytes(url: str) -> bytes:
  headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "RepoWorkflow-authenticated-cache",
  }
  token = os.getenv("GITHUB_TOKEN")
  if token:
    headers["Authorization"] = "Bearer " + token
  opener = build_opener(_StripCrossHostAuthorization())
  with opener.open(Request(url, headers=headers), timeout=15) as response:
    data = response.read(_MAX_ARCHIVE + 1)
  if len(data) > _MAX_ARCHIVE:
    raise ValueError("provider artifact exceeds verification limit")
  return data


def verify_hosted_record(
  record: dict, *, repo: str, stage: str,
  read: Callable[[str], dict] = github_json,
  download: Callable[[str], bytes] = _artifact_bytes,
) -> bool:
  """Reject fabricated PASS groups, stale replay and unavailable artifacts."""
  if not isinstance(record, dict):
    return False
  if not verify_hosted_stage(record, repo=repo, stage=stage, read=read):
    return False
  run_id = record["providerRunId"]
  candidate = record["providerCandidateSHA"]
  branch = record.get("branch")
  kind = {
    "GREEN-testing": "GREEN", "temp-testing": "temporary",
    "RED-testing": "RED", "regression-testing": "regression",
    "integration-testing": "integration",
  }[stage]
  if (
    record.get("runner") != "github-actions"
    or record.get("kind") != kind
    or record.get("result") != "succeeded"
    or record.get("testSHA") != candidate
    or not isinstance(branch, str)
  ):
    return False
  branch_match = re.fullmatch(r"issue-([1-9][0-9]*)(?:-[A-Za-z0-9_.-]+)?", branch)
  if branch_match is None:
    return False
  base = "https://api.github.com/repos/" + repo
  try:
    listing = read(base + "/actions/runs/" + str(run_id) + "/artifacts?per_page=100")
    if not isinstance(listing, dict):
      return False
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
      return False
    matching = [
      a for a in artifacts if isinstance(a, dict)
      and a.get("name") == "provider-result-" + str(run_id)
      and a.get("expired") is False
      and type(a.get("id")) is int and a["id"] > 0
      and type(a.get("size_in_bytes")) is int and a["size_in_bytes"] > 0
    ]
    if len(matching) != 1:
      return False
    artifact = matching[0]
    url = base + "/actions/artifacts/" + str(artifact["id"]) + "/zip"
    archive = download(url)
    if not isinstance(archive, bytes) or len(archive) > _MAX_ARCHIVE:
      return False
    with ZipFile(BytesIO(archive)) as zipped:
      wanted = "testResults-" + branch_match.group(1) + ".jsonl"
      if zipped.namelist() != [wanted]:
        return False
      entry = zipped.getinfo(wanted)
      if entry.file_size > _MAX_ARCHIVE:
        return False
      raw = zipped.read(wanted).decode("utf-8")
    observations = [json.loads(line) for line in raw.splitlines()]
    if not observations or not all(isinstance(x, dict) for x in observations):
      return False
    return sum(x == record for x in observations) == 1
  except (OSError, KeyError, ValueError, TypeError, UnicodeError, BadZipFile,
          HTTPError, URLError, TimeoutError, json.JSONDecodeError):
    return False
