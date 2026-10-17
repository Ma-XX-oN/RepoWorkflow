"""Scoped GitHub integration ref read/create primitives (issue #681).

Operations not implemented here (atomic ref CAS, destination lease CAS and
authoritative outcomes) remain UNSUPPORTED, not simulated.
"""
import re


class IntegrationProviderError(RuntimeError):
  """An integration mutation is unverified or cannot be supported."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REF = re.compile(r"refs/heads/INT-ATTEMPT-issue-[1-9][0-9]*/.+\Z")


def inventory_ready_refs(backend):
  """Discover READY submissions; reject possible partial pagination."""
  try:
    payload = backend.get("git/matching-refs/heads/PRELIM-?per_page=100")
  except Exception as error:
    raise IntegrationProviderError("PRELIM inventory is unavailable") from error
  if type(payload) is not list:
    raise IntegrationProviderError("PRELIM inventory has invalid shape")
  if len(payload) >= 100:
    raise IntegrationProviderError("PRELIM inventory may be paginated")
  refs = {}
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
  return refs


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
