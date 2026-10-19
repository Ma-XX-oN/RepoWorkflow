"""Scoped GitHub integration ref read/create primitives (issue #681).

Operations not implemented here (atomic ref CAS, destination lease CAS and
authoritative outcomes) remain UNSUPPORTED, not simulated.
"""
import re


class IntegrationProviderError(RuntimeError):
  """An integration mutation is unverified or cannot be supported."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REF = re.compile(r"refs/heads/INT-ATTEMPT-[A-Za-z0-9._-]+/.+\Z")


def inventory_ready_refs(backend, *, max_pages=100):
  """Discover every published PRELIM ref, failing on truncated inventory."""
  if type(max_pages) is not int or max_pages < 1:
    raise IntegrationProviderError("invalid pagination bound")
  refs = {}
  for page in range(1, max_pages + 1):
    route = ("git/matching-refs/heads/PRELIM-"
             f"?per_page=100&page={page}")
    try:
      payload = backend.get(route)
    except Exception as error:
      raise IntegrationProviderError("PRELIM inventory is unavailable") from error
    if type(payload) is not list or len(payload) > 100:
      raise IntegrationProviderError("PRELIM inventory page is invalid")
    for entry in payload:
      if (type(entry) is not dict or type(entry.get("ref")) is not str
          or type(entry.get("object")) is not dict):
        raise IntegrationProviderError("PRELIM inventory contains invalid ref")
      ref = entry["ref"]
      sha = entry["object"].get("sha")
      if (not ref.startswith("refs/heads/PRELIM-")
          or type(sha) is not str or _SHA.fullmatch(sha) is None
          or ref in refs):
        raise IntegrationProviderError("PRELIM inventory identity is invalid")
      refs[ref] = sha
    if len(payload) < 100:
      return refs
  raise IntegrationProviderError("PRELIM inventory exceeded pagination bound")


def _read_ref(backend, ref):
  try:
    result = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise IntegrationProviderError("provider ref read is unavailable") from error
  if (type(result) is not dict or result.get("ref") != ref
      or type(result.get("object")) is not dict):
    raise IntegrationProviderError("provider ref identity is invalid")
  sha = result["object"].get("sha")
  if type(sha) is not str or _SHA.fullmatch(sha) is None:
    raise IntegrationProviderError("provider ref SHA is invalid")
  return sha


def create_int_attempt(backend, request, *, authorized):
  """Create-if-absent; reconcile uncertain reply with authoritative readback."""
  ref = request.get("parameters", {}).get("ref")
  sha = request.get("parameters", {}).get("sha")
  if (authorized is not True or type(ref) is not str
      or _REF.fullmatch(ref) is None or type(sha) is not str
      or _SHA.fullmatch(sha) is None):
    raise IntegrationProviderError("INT-ATTEMPT mutation not authorized or invalid")
  try:
    fresh = backend.reserve(request)
  except Exception as error:
    raise IntegrationProviderError("request reservation outcome UNKNOWN") from error
  observed = _read_ref(backend, ref)
  if not fresh:
    if observed != sha:
      raise IntegrationProviderError("reserved request lacks matching ref")
    return "unchanged", {"ref": ref, "sha": sha}
  if observed is not None:
    raise IntegrationProviderError("INT-ATTEMPT ref already exists")
  try:
    backend.post("git/refs", {"ref": ref, "sha": sha})
  except Exception:
    if _read_ref(backend, ref) != sha:
      raise IntegrationProviderError("ref publication outcome UNKNOWN")
  if _read_ref(backend, ref) != sha:
    raise IntegrationProviderError("published INT-ATTEMPT SHA differs")
  return "applied", {"ref": ref, "sha": sha}


def cas_int_attempt_git(root, remote, ref, expected_sha, new_sha):
  """Git-protocol expected-old-SHA update restricted to INT-ATTEMPT.

  The caller must provide a trusted configured remote and repository checkout,
  including the new commit object. A failed or lost response is not PASS.
  """
  import subprocess
  from pathlib import Path

  if (type(ref) is not str or _REF.fullmatch(ref) is None
      or type(expected_sha) is not str or _SHA.fullmatch(expected_sha) is None
      or type(new_sha) is not str or _SHA.fullmatch(new_sha) is None
      or type(remote) is not str or not remote or remote.startswith("-")):
    raise IntegrationProviderError("invalid INT-ATTEMPT CAS identity")
  if any(part in ("", ".", "..") for part in ref.split("/")):
    raise IntegrationProviderError("unsafe INT-ATTEMPT CAS ref")
  if expected_sha == new_sha:
    raise IntegrationProviderError("CAS requires changed commit")
  root = Path(root)
  def run(*args):
    try:
      return subprocess.run(["git", "-C", str(root), *args],
        capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
      raise IntegrationProviderError("Git CAS outcome UNKNOWN") from error

  if run("cat-file", "-e", new_sha + "^{commit}").returncode:
    raise IntegrationProviderError("new INT-ATTEMPT commit is unavailable")
  command = ("push", "--porcelain",
             "--force-with-lease=" + ref + ":" + expected_sha,
             remote, new_sha + ":" + ref)
  result = run(*command)
  readback = run("ls-remote", "--heads", remote, ref)
  if readback.returncode:
    raise IntegrationProviderError("INT-ATTEMPT CAS readback UNKNOWN")
  lines = readback.stdout.splitlines()
  if len(lines) != 1 or lines[0].split()[-1] != ref:
    raise IntegrationProviderError("INT-ATTEMPT CAS identity unavailable")
  observed_sha = lines[0].split()[0]
  if result.returncode:
    if observed_sha != expected_sha:
      raise IntegrationProviderError("INT-ATTEMPT CAS failed or outcome UNKNOWN")
    raise IntegrationProviderError("INT-ATTEMPT CAS provider rejected update")
  if observed_sha != new_sha:
    raise IntegrationProviderError("INT-ATTEMPT CAS readback differs")
  return {"ref": ref, "sha": new_sha}
