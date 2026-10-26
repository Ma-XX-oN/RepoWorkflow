"""Idempotent terminal result tags for an already versioned test candidate.

Callers resolve the original candidate and its development version BEFORE
creating an on-demand CI request. This module does not choose version numbers.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import re
import stat
import subprocess

from .phase_terminal import PhaseTransitionError, plan_phase


_VERSION_RE = re.compile(
  r"[0-9]+\.[0-9]+\.[0-9]+-issue\.[1-9][0-9]*\.[0-9]+\.[0-9]+"
)
_SHA_RE = re.compile(r"[0-9a-f]{40}")


class TerminalTagError(ValueError):
  pass


def _reject_json_constant(value: str) -> None:
  raise ValueError("non-standard JSON constant: " + value)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
  values = {}
  for key, value in pairs:
    if key in values:
      raise ValueError("duplicate JSON key: " + key)
    values[key] = value
  return values


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=False,
  )
  if check and result.returncode:
    raise TerminalTagError(
      "git " + args[0] + " failed: " + result.stderr.strip()
    )
  return result


def _local_target(root: Path, tag: str) -> str | None:
  ref = "refs/tags/" + tag
  exists = _git(root, "show-ref", "--verify", "--quiet", ref, check=False)
  if exists.returncode == 1:
    return None
  if exists.returncode:
    raise TerminalTagError("cannot establish local terminal tag state")
  kind = _git(root, "cat-file", "-t", ref).stdout.strip()
  if kind != "tag":
    raise TerminalTagError("terminal tag must be annotated: " + tag)
  return _git(root, "rev-parse", ref + "^{commit}").stdout.strip()


def _remote_target(root: Path, remote: str, tag: str) -> str | None:
  ref = "refs/tags/" + tag
  result = _git(root, "ls-remote", "--tags", remote, ref, ref + "^{}")
  observed = dict(
    (line.split("\t", 1)[1], line.split("\t", 1)[0])
    for line in result.stdout.splitlines()
    if "\t" in line
  )
  if not observed:
    return None
  if ref not in observed or ref + "^{}" not in observed:
    raise TerminalTagError("remote terminal tag is not annotated: " + tag)
  target = observed[ref + "^{}"]
  if _SHA_RE.fullmatch(target) is None:
    raise TerminalTagError("invalid remote terminal tag target")
  return target


def _canonical_evidence_log(root: Path, supplied: Path) -> Path:
  """Return the sole canonical evidence file after checking filesystem identity.

  The repository root may be reached through any legitimate filesystem alias.
  Directory and file identities are compared with Path.samefile, not textual
  spellings. Components below that root cannot be links or reparse redirects.
  """
  invalid = "canonical test log must use repository validation path"
  if ".." in supplied.parts:
    raise TerminalTagError(invalid)
  try:
    repository = root.resolve(strict=True)
    validation_root = repository / ".repoworkflow"
    validation_dir = validation_root / "validation"
    expected = validation_dir / supplied.name
    parts = (
      (supplied.parent.parent.parent, repository, True, False),
      (supplied.parent.parent, validation_root, True, True),
      (supplied.parent, validation_dir, True, True),
      (supplied, expected, False, True),
    )
    for observed, trusted, is_directory, protected in parts:
      # Once the parent identities are proven, a missing canonical log is
      # unavailable evidence, not a foreign path.
      if not is_directory and not expected.exists() and not expected.is_symlink():
        raise TerminalTagError("canonical testing log is unavailable")
      if not observed.samefile(trusted):
        raise TerminalTagError(invalid)
      if protected:
        for path in (observed, trusted):
          mode = path.lstat()
          if (
            stat.S_ISLNK(mode.st_mode)
            or getattr(mode, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            or not (
              stat.S_ISDIR(mode.st_mode)
              if is_directory else stat.S_ISREG(mode.st_mode)
            )
          ):
            raise TerminalTagError(invalid)
    return expected
  except (OSError, RuntimeError) as error:
    raise TerminalTagError(invalid) from error


def verify_phase_evidence(
  root: Path, canonical_log: Path, *, stage: str, version: str,
  candidate: str, outcome: str,
) -> None:
  """Require matching issue, phase, candidate and terminal result evidence."""
  issue = re.fullmatch(
    r"testResults-([1-9][0-9]*)\.jsonl", canonical_log.name,
  )
  version_issue = _VERSION_RE.fullmatch(version)
  if issue is None or version_issue is None:
    raise TerminalTagError("canonical evidence requires a per-issue versioned log")
  expected_issue = version.split("-issue.", 1)[1].split(".", 1)[0]
  if issue.group(1) != expected_issue:
    raise TerminalTagError("test log issue differs from development version")
  canonical_file = _canonical_evidence_log(root, canonical_log)
  try:
    with canonical_file.open("rb") as evidence:
      # The pathname can change between validation and open. Bind the
      # evidence to its opened filesystem object, and revalidate after read.
      opened = os.fstat(evidence.fileno())
      invalid = "canonical test log must use repository validation path"
      if not os.path.samestat(opened, canonical_file.stat()):
        raise TerminalTagError(invalid)
      _canonical_evidence_log(root, canonical_log)
      raw = evidence.read()
      _canonical_evidence_log(root, canonical_log)
      if not os.path.samestat(opened, canonical_file.stat()):
        raise TerminalTagError(invalid)
    lines = raw.decode("utf-8", errors="strict").split("\n")
    if lines[-1] == "":
      lines.pop()
  except UnicodeError as error:
    raise TerminalTagError("canonical testing log is malformed") from error
  except OSError as error:
    raise TerminalTagError("canonical testing log is unavailable") from error
  observed = []
  wrong_phase = False
  for line in lines:
    try:
      record = json.loads(
        line, parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
      )
    except (json.JSONDecodeError, ValueError) as error:
      raise TerminalTagError("canonical testing log is malformed") from error
    if not isinstance(record, dict):
      raise TerminalTagError("canonical testing log contains a non-object")
    if record.get("testVersion") == version:
      if record.get("kind") == stage:
        observed.append(record)
      else:
        wrong_phase = True
  if not observed:
    if wrong_phase:
      raise TerminalTagError("development version belongs to another phase")
    raise TerminalTagError("no canonical evidence for development version")
  for record in observed:
    branch = record.get("branch")
    if (not isinstance(branch, str)
        or re.fullmatch(
          r"issue-" + re.escape(expected_issue) + r"(?:-.*)?", branch,
        ) is None):
      raise TerminalTagError("canonical evidence branch differs from issue")
    if record.get("kind") != stage or record.get("testSHA") != candidate:
      raise TerminalTagError("development version belongs to another phase or candidate")
  expected = "succeeded" if outcome == "PASS" else "failed"
  terminal = {
    record.get("result") for record in observed
    if record.get("result") in ("succeeded", "failed")
  }
  if terminal != {expected}:
    raise TerminalTagError("canonical evidence has conflicting terminal outcome")
  matching = [
    record for record in observed
    if record.get("result") == expected
    and record.get("headChangedDuringTest") is False
    and record.get("uncommittedChanges") == []
    and (outcome == "FAIL" or record.get("reusable") is True)
  ]
  if not matching:
    raise TerminalTagError("canonical evidence does not establish terminal outcome")


def publish_terminal_tag(
  root: Path, *, stage: str, remote: str, version: str,
  candidate: str, outcome: str, canonical_log: Path,
  push: bool = True,
) -> str | None:
  """Publish exactly one immutable result, or reuse the identical result."""
  if stage not in {"regression", "integration"}:
    raise TerminalTagError("terminal tags require regression or integration")
  if outcome == "INCOMPLETE":
    return None
  if outcome not in {"PASS", "FAIL"}:
    raise TerminalTagError("unknown terminal testing outcome")
  if _VERSION_RE.fullmatch(version) is None:
    raise TerminalTagError("terminal testing requires a development version")
  if _SHA_RE.fullmatch(candidate) is None:
    raise TerminalTagError("terminal tag requires a full original candidate SHA")
  resolved = _git(
    root, "rev-parse", "--verify", candidate + "^{commit}",
  ).stdout.strip()
  if resolved != candidate:
    raise TerminalTagError("candidate does not identify an exact commit")
  verify_phase_evidence(
    root, canonical_log, stage=stage, version=version,
    candidate=candidate, outcome=outcome,
  )
  try:
    tag = plan_phase(version, phase=stage, outcome=outcome).terminal_tag
    opposite_outcome = "FAIL" if outcome == "PASS" else "PASS"
    opposite = plan_phase(
      version, phase=stage, outcome=opposite_outcome,
    ).terminal_tag
  except PhaseTransitionError as error:
    raise TerminalTagError("invalid terminal phase/version") from error
  for other in (opposite,):
    if _local_target(root, other) is not None:
      raise TerminalTagError("opposite terminal outcome already exists")
    if push and _remote_target(root, remote, other) is not None:
      raise TerminalTagError("opposite remote terminal outcome already exists")
  local = _local_target(root, tag)
  published = _remote_target(root, remote, tag) if push else None
  if local is not None and local != candidate:
    raise TerminalTagError("local terminal tag targets a different commit")
  if published is not None:
    if published != candidate:
      raise TerminalTagError("remote terminal tag targets a different commit")
    if local is None and not push:
      _git(root, "tag", "-a", tag, candidate, "-m", tag)
    return tag
  if local is None:
    created = _git(root, "tag", "-a", tag, candidate, "-m", tag, check=False)
    if created.returncode and _local_target(root, tag) != candidate:
      raise TerminalTagError("terminal tag creation failed")
  if not push:
    return tag
  pushed = _git(
    root, "push", remote, "refs/tags/" + tag, check=False,
  )
  if pushed.returncode:
    # Concurrent identical publication is harmless; a different target is not.
    if _remote_target(root, remote, tag) != candidate:
      raise TerminalTagError("terminal tag publication failed")
  return tag
