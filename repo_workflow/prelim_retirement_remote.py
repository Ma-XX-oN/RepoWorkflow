"""Conditional remote cleanup after authoritative #103 retirement preflight.

Never invoke this for an unverified PRELIM submission. Delete only this
attempt's named ref with exact old SHA; a stale ref remains untouched.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .prelim_retirement import (
  RetirementPlan, PrelimRetirementError,
)


_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class RefRetirement:
  ref: str
  previously_observed_sha: str
  absent_after: bool


def retire_verified_ref(
    root: Path, remote: str, plan: RetirementPlan,
    ref: str, expected_sha: str,
) -> RefRetirement:
  """Conditional delete-and-readback; ambiguous results fail closed.

  Any durable retirement event remains the caller's responsibility. Recheck
  ref identity, exact original SHA and terminal proof on every attempt.
  """
  if (not isinstance(plan, RetirementPlan)
      or plan.eligible_for_ref_retirement is not True
      or type(ref) is not str
      or ref not in (plan.prelim_ref, plan.int_attempt_ref)
      or type(expected_sha) is not str or _SHA.fullmatch(expected_sha) is None
      or type(remote) is not str or not remote or remote.startswith("-")
      or not plan.terminal_evidence_ref):
    raise PrelimRetirementError("remote retirement is not authorized")
  if not (ref.startswith("refs/heads/PRELIM-issue-") or
          ref.startswith("refs/heads/INT-ATTEMPT-issue-")):
    raise PrelimRetirementError("ref is outside the permitted attempt")
  root = Path(root)
  def run(*args):
    try:
      return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise PrelimRetirementError("remote retirement outcome UNKNOWN") from error

  def read():
    result = run("ls-remote", "--heads", remote, ref)
    if result.returncode:
      raise PrelimRetirementError("remote retirement readback UNKNOWN")
    rows = result.stdout.strip().splitlines()
    if not rows:
      return None
    if len(rows) != 1:
      raise PrelimRetirementError("remote ref identity ambiguous")
    fields = rows[0].split()
    if len(fields) != 2 or fields[1] != ref or _SHA.fullmatch(fields[0]) is None:
      raise PrelimRetirementError("remote ref identity malformed")
    return fields[0]

  current = read()
  if current != expected_sha:
    raise PrelimRetirementError("remote ref changed or already retired")
  result = run(
    "push", "--porcelain",
    "--force-with-lease=" + ref + ":" + expected_sha,
    remote, ":" + ref,
  )
  after = read()
  if result.returncode or after is not None:
    raise PrelimRetirementError("remote retirement rejected or UNKNOWN")
  return RefRetirement(ref, expected_sha, True)
