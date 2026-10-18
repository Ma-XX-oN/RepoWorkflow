"""Safe fast-forward of an inactive local main after verified integration.

Never reset a checked-out worktree and never discard local commits. The
caller first verifies authoritative landing and obtains RetirementPlan.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .prelim_retirement import RetirementPlan, PrelimRetirementError
from .prelim_retirement_remote import authenticated_remote_endpoint


_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class MainResync:
  old_sha: str
  new_sha: str
  changed: bool


def resync_inactive_main(root: Path, remote: str,
    plan: RetirementPlan, *, backend) -> MainResync:
  """Fast-forward local main without checking it out or altering user files."""
  if (not isinstance(plan, RetirementPlan)
      or plan.eligible_for_ref_retirement is not True
      or not plan.terminal_evidence_ref
      or type(remote) is not str
      or not re.fullmatch(r"[A-Za-z0-9._-]+", remote)):
    raise PrelimRetirementError("verified integration and safe remote required")
  root = Path(root)
  def command(*args):
    try:
      return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise PrelimRetirementError("local main resync unavailable") from error

  local = command("rev-parse", "--verify", "refs/heads/main")
  if local.returncode:
    raise PrelimRetirementError("local main is missing")
  old = local.stdout.strip()
  if _SHA.fullmatch(old) is None:
    raise PrelimRetirementError("local main SHA malformed")
  # Verify both provider repository identity and the exact authoritative tip.
  endpoint = authenticated_remote_endpoint(root, remote, backend)
  try:
    observed = backend.get("git/ref/heads/main")
  except Exception as error:
    raise PrelimRetirementError("provider main readback unavailable") from error
  if (type(observed) is not dict or observed.get("ref") != "refs/heads/main"
      or type(observed.get("object")) is not dict):
    raise PrelimRetirementError("provider main identity mismatch")
  server_tip = observed["object"].get("sha")
  if type(server_tip) is not str or _SHA.fullmatch(server_tip) is None:
    raise PrelimRetirementError("provider main SHA invalid")
  fetched = command("fetch", "--no-tags", endpoint, "refs/heads/main")
  if fetched.returncode:
    raise PrelimRetirementError("remote main fetch unavailable")
  new_result = command("rev-parse", "--verify", "FETCH_HEAD")
  if new_result.returncode:
    raise PrelimRetirementError("fetched remote main unavailable")
  new = new_result.stdout.strip()
  if _SHA.fullmatch(new) is None:
    raise PrelimRetirementError("remote main SHA malformed")
  if new != server_tip:
    raise PrelimRetirementError("fetched main differs from provider readback")
  for ancestor in (plan.landed_sha, old):
    if command("merge-base", "--is-ancestor", ancestor, new).returncode:
      raise PrelimRetirementError("main fast-forward or landing not proved")
  if old == new:
    return MainResync(old, new, False)
  worktrees = command("worktree", "list", "--porcelain")
  if worktrees.returncode:
    raise PrelimRetirementError("local worktree ownership unavailable")
  if any(line == "branch refs/heads/main"
         for line in worktrees.stdout.splitlines()):
    raise PrelimRetirementError("main is checked out or update failed")
  # update-ref's third argument is the expected old SHA: another local
  # writer advancing main in the meantime must win rather than be reset.
  updated = command("update-ref", "refs/heads/main", new, old)
  if updated.returncode:
    raise PrelimRetirementError("main moved concurrently or update failed")
  final = command("rev-parse", "--verify", "refs/heads/main")
  if final.returncode or final.stdout.strip() != new:
    raise PrelimRetirementError("local main resync readback mismatch")
  return MainResync(old, new, True)
