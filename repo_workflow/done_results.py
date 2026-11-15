"""Reuse actual catalogue results and publish immutable PRELIM test reports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform

from .git import git
from .owned_commit import commit_owned_files
from .source_tip import source_tip
from .test_catalogue import stage_groups
from .test_results_reader import parse_testing_log, TestCommandError


def platform_name(value: str | None = None) -> str:
  """Return the repository platform name for an OS observation.

  Parameters
  ----------
  value : str, optional
      OS name, defaulting to the actual executing platform.

  Returns
  -------
  str
      Normalized platform identity.
  """
  name = (value or platform.system()).lower()
  return {"darwin": "macos", "win32": "windows"}.get(name, name)


def log_path(root: Path, issue: int) -> Path:
  """Locate the canonical per-issue report.

  Parameters
  ----------
  root : Path
      Candidate checkout.
  issue : int
      Issue number.

  Returns
  -------
  Path
      Canonical JSONL location.
  """
  return root / f".repoworkflow/validation/testResults-{issue}.jsonl"


def records(root: Path, plan: dict) -> list[dict]:
  """Read results and stop on any failure for the effective candidate.

  Parameters
  ----------
  root : Path
      Checkout containing report objects.
  plan : dict
      Exact candidate/issue/parent identity.

  Returns
  -------
  list of dict
      Original reports, including historical results.
  """
  path = log_path(root, plan["issue"])
  rows = parse_testing_log(path.read_bytes().decode("utf-8")) if path.exists() else []
  for row in rows:
    if row["result"] == "failed" and source_tip(root, row["testSHA"]) == plan["candidate_sha"]:
      raise TestCommandError("current source has a failed test; repair before done")
  return rows


def pending_groups(root: Path, plan: dict, stage: str, os_name: str) -> tuple[str, ...]:
  """Select only tests without applicable passing observations.

  Parameters
  ----------
  root : Path
      Exact candidate checkout.
  plan : dict
      Pinned source, parent and relevant-input identities.
  stage, os_name : str
      Catalogue stage and required platform (or any).

  Returns
  -------
  tuple of str
      Remaining registered catalogue groups.
  """
  fingerprint = hashlib.sha256((root / ".ci/tests.json").read_bytes()).hexdigest()
  passed = set()
  for row in records(root, plan):
    if (row["testSHA"] != plan["candidate_sha"]
        or row["result"] != "succeeded" or row["kind"] == "RED"
        or row.get("catalogueSHA256") != fingerprint
        or row.get("uncommittedChanges") != []
        or row.get("headChangedDuringTest") is not False
        or row.get("doneParentSHA", plan["parent_sha"]) != plan["parent_sha"]
        or row.get("doneInputsSHA256", plan["inputs_sha256"]) != plan["inputs_sha256"]):
      continue
    observed = platform_name(row.get("platform", {}).get("os", "unknown"))
    if os_name != "any" and observed != os_name:
      continue
    groups = row.get("groups")
    if groups is not None:
      passed.update(item["group"] for item in groups if item.get("exit_code") == 0)
    passed.update(row.get("selectedGroups", []))
  return tuple(group for group in stage_groups(root, stage) if group not in passed)


def import_reports(root: Path, plan: dict) -> None:
  """Append previously published platform/manual reports without rerunning tests.

  Parameters
  ----------
  root : Path
      Candidate checkout receiving reports.
  plan : dict
      Submission identity and authoritative Git remote.
  """
  path = log_path(root, plan["issue"])
  previous = path.read_bytes() if path.exists() else b""
  known = {json.dumps(row, sort_keys=True) for row in
           parse_testing_log(previous.decode("utf-8"))} if previous else set()
  added = []
  prefix = "refs/tags/rwf-prelim-results-v1-" + plan["version_suffix"] + "-"
  advertised = git(root, "ls-remote", "--refs", plan["remote"], prefix + "*").stdout
  for line in sorted(advertised.splitlines()):
    _, ref = line.split("\t")
    git(root, "fetch", "--no-tags", plan["remote"], ref)
    report = git(root, "rev-parse", "FETCH_HEAD").stdout.strip()
    if source_tip(root, report) != plan["candidate_sha"]:
      raise TestCommandError("published report differs from selected PRELIM source")
    raw = git(root, "show", report + ":" + path.relative_to(root).as_posix()).stdout
    for row in parse_testing_log(raw):
      encoded = json.dumps(row, sort_keys=True)
      if encoded not in known:
        known.add(encoded)
        added.append(encoded)
  if added:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(previous + ("\n".join(added) + "\n").encode("utf-8"))
    commit_owned_files(root, [path.relative_to(root).as_posix()], "test: collect PRELIM platform reports")
  records(root, plan)


def publish_report(root: Path, plan: dict) -> str | None:
  """Retain a report-only commit through an immutable content-named Git tag.

  Parameters
  ----------
  root : Path
      Checkout containing actual test results.
  plan : dict
      Submission identity and remote.

  Returns
  -------
  str or None
      Report ref, or None when no report exists.
  """
  path = log_path(root, plan["issue"])
  if not path.exists():
    return None
  relative = path.relative_to(root).as_posix()
  commit_owned_files(root, [relative], "test: record PRELIM test results")
  report = git(root, "rev-parse", "HEAD").stdout.strip()
  if source_tip(root, report) != plan["candidate_sha"]:
    raise TestCommandError("tests changed source; prepare and test a new candidate")
  digest = hashlib.sha256(path.read_bytes()).hexdigest()
  ref = "refs/tags/rwf-prelim-results-v1-" + plan["version_suffix"] + "-" + digest
  advertised = git(root, "ls-remote", "--refs", plan["remote"], ref).stdout.split()
  if not advertised:
    git(root, "push", "--force-with-lease=" + ref + ":", plan["remote"], report + ":" + ref)
  return ref
