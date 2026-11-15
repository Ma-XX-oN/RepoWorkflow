"""Resolve material Git source through append-only testing-report commits.

Report recognition establishes source identity only. It does not authenticate
the reported PASS; evidence consumers must still verify their own authorities.
"""
from pathlib import Path
import re

from .git import git
from .test_results_reader import TestCommandError, parse_testing_log

_REPORT = re.compile(r"\.repoworkflow/validation/testResults-[1-9][0-9]*\.jsonl\Z")


def source_tip(root: Path, revision: str = "HEAD") -> str:
  """Resolve source without treating arbitrary subjects as report commits.

  Parameters
  ----------
  root : Path
      Git repository.
  revision : str
      Commit to resolve.

  Returns
  -------
  str
      Material source SHA. Mixed, rewritten or malformed reports are material.
  """
  cursor = git(root, "rev-parse", "--verify", revision + "^{commit}").stdout.rstrip("\r\n")
  reports = []
  for _ in range(512):
    parents = git(root, "rev-list", "--parents", "-n", "1", cursor).stdout.split()
    if len(parents) != 2:
      break
    parent = parents[1]
    paths = git(root, "diff-tree", "--no-commit-id", "--name-only", "-z",
                "-r", cursor).stdout.removesuffix("\0").split("\0")
    if not paths or any(_REPORT.fullmatch(path) is None for path in paths):
      break
    additions = []
    valid_report = True
    for path in paths:
      before = git(root, "show", parent + ":" + path, check=False)
      after = git(root, "show", cursor + ":" + path).stdout
      old = before.stdout if before.returncode == 0 else ""
      if (before.returncode not in (0, 128) or not after.startswith(old)
          or old and not old.endswith("\n") or not after.endswith("\n")):
        valid_report = False
        break
      try:
        rows = parse_testing_log(after[len(old):])
      except (TestCommandError, ValueError, TypeError, RecursionError):
        valid_report = False
        break
      if not rows or any(not isinstance(row, dict)
                         or row.get("result") not in {"succeeded", "failed", "incomplete", "skipped"}
                         or not re.fullmatch(r"[0-9a-f]{40}", str(row.get("testSHA", "")))
                         for row in rows):
        valid_report = False
        break
      additions.extend(rows)
    if not valid_report:
      break
    reports.append((cursor, parent, additions))
    cursor = parent
  # Every report must refer to the material tip or a prior report in this
  # exact chain. A fabricated report for unrelated source is not peeled.
  accepted = {cursor}
  for report, parent, rows in reversed(reports):
    if parent not in accepted or any(row["testSHA"] not in accepted for row in rows):
      return report
    accepted.add(report)
  return cursor
