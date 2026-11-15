"""Scoped GitHub integration ref inventory primitives (issue #681).

Operations not implemented here (atomic ref CAS, destination lease CAS and
authoritative outcomes) remain UNSUPPORTED, not simulated.
"""
import re


class IntegrationProviderError(RuntimeError):
  """An integration mutation is unverified or cannot be supported."""


_SHA = re.compile(r"[0-9a-f]{40}\Z")


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
