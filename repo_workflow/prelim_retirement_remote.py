"""Repository-bound conditional cleanup after authoritative #103 proof.

No arbitrary Git remote is authorized. Bind the configured remote to the
independently authenticated provider repository before even reading a ref.
Delete only this attempt's named ref with exact old SHA.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .prelim_retirement import (
  RetirementPlan, PrelimRetirementError, verify_attempt_scope,
)


_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class RefRetirement:
  ref: str
  previously_observed_sha: str
  absent_after: bool


def authenticated_remote_endpoint(root: Path, remote: str, backend) -> str:
  """Confirm the Git remote is the provider's exact scoped repository URL."""
  repository = getattr(backend, "repository", None)
  if type(repository) is not str or not repository:
    raise PrelimRetirementError("authenticated repository is unavailable")
  try:
    details = backend.get("")
  except Exception as error:
    raise PrelimRetirementError("repository identity readback unavailable") from error
  if type(details) is not dict or details.get("full_name") != repository:
    raise PrelimRetirementError("authenticated repository identity mismatch")
  approved = {
    value for value in (details.get("clone_url"), details.get("ssh_url"))
    if type(value) is str and value and "\\n" not in value
  }
  if not approved:
    raise PrelimRetirementError("authenticated repository URL unavailable")
  def get_url(*args):
    try:
      return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise PrelimRetirementError("repository remote readback UNKNOWN") from error
  fetch_url = get_url("remote", "get-url", remote)
  push_url = get_url("remote", "get-url", "--push", remote)
  if (fetch_url.returncode or push_url.returncode
      or fetch_url.stdout.strip() != push_url.stdout.strip()
      or fetch_url.stdout.strip() not in approved):
    raise PrelimRetirementError("Git remote differs from authenticated repository")
  # Use the verified URL rather than the mutable alias at mutation time.
  return fetch_url.stdout.strip()


def retire_verified_ref(
    root: Path, remote: str, plan: RetirementPlan,
    ref: str, expected_sha: str, *, backend,
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
  verify_attempt_scope(plan.prelim_ref, plan.int_attempt_ref)
  if not (ref.startswith("refs/heads/PRELIM-") or
          ref.startswith("refs/heads/INT-ATTEMPT-")):
    raise PrelimRetirementError("ref is outside the permitted attempt")
  root = Path(root)
  def run(*args):
    try:
      return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise PrelimRetirementError("remote retirement outcome UNKNOWN") from error

  endpoint = authenticated_remote_endpoint(root, remote, backend)

  def read():
    result = run("ls-remote", "--heads", endpoint, ref)
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
    endpoint, ":" + ref,
  )
  after = read()
  if result.returncode or after is not None:
    raise PrelimRetirementError("remote retirement rejected or UNKNOWN")
  return RefRetirement(ref, expected_sha, True)
