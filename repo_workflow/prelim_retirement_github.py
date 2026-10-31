"""Read-only GitHub facts for #103 retirement evidence verification."""
from urllib.parse import quote

from .prelim_retirement import (
  LandedIntegration, PrelimRetirementError,
)
from .prelim_retirement_evidence import verify_retirement_evidence


def verify_github_retirement(backend, landed: LandedIntegration,
    read_terminal):
  """Verify current GitHub ref/compare facts and durable terminal ledger.

  backend is the configured authenticated repository provider, with get
  restricted to this repository. read_terminal must independently retrieve
  immutable evidence, not return facts from the submitted PRELIM.
  """
  def read_ref(ref):
    if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
      raise PrelimRetirementError("invalid GitHub ref")
    route = "git/ref/" + quote(ref.removeprefix("refs/"), safe="/")
    try:
      response = backend.get(route)
    except Exception as error:
      if getattr(error, "code", None) == "not_found":
        return None
      raise PrelimRetirementError("GitHub ref read unavailable") from error
    if (type(response) is not dict or response.get("ref") != ref
        or type(response.get("object")) is not dict):
      raise PrelimRetirementError("GitHub ref response identity mismatch")
    return response["object"].get("sha")

  def compare(base, head):
    if not all(isinstance(x, str) and len(x) == 40
               for x in (base, head)):
      raise PrelimRetirementError("comparison commit identity invalid")
    try:
      response = backend.get("compare/" + base + "..." + head)
    except Exception as error:
      raise PrelimRetirementError("GitHub ancestry unavailable") from error
    if (type(response) is not dict
        or type(response.get("base_commit")) is not dict
        or type(response.get("merge_base_commit")) is not dict):
      raise PrelimRetirementError("GitHub comparison response malformed")
    # GitHub's REST compare response supplies base_commit and
    # merge_base_commit, not head_commit. The authenticated request URL
    # pins the exact head; the merge base proves ancestry independently.
    if response["merge_base_commit"].get("sha") != base:
      raise PrelimRetirementError("GitHub merge base differs from landed commit")
    return {
      "base_sha": response["base_commit"].get("sha"),
      "head_sha": head,
      "status": response.get("status"),
      "behind_by": response.get("behind_by"),
    }

  return verify_retirement_evidence(
    landed, read_ref=read_ref, compare_commits=compare,
    read_terminal=read_terminal,
  )
