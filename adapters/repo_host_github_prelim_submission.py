"""Read exact immutable PRELIM provenance from the authoritative Git provider."""
import re

from repo_workflow.prelim_submission import (
  SubmissionError, decode_submission, submission_ref,
)


def read_submission(backend, guid):
  """Read a receipt and verify its physical candidate and historical parent.

  Parameters
  ----------
  backend : GitHubBackend
      Authenticated repository provider.
  guid : str
      Submission identity independently discovered from a PRELIM ref.

  Returns
  -------
  dict or None
      Immutable provenance, or None if no receipt exists. Missing/invalid
      provenance never establishes order or test readiness.
  """
  ref = submission_ref(guid)
  try:
    response = backend.get("git/ref/" + ref.removeprefix("refs/"))
  except Exception as error:
    if getattr(error, "code", None) == "not_found":
      return None
    raise SubmissionError("submission provider read UNKNOWN") from error
  if (type(response) is not dict or response.get("ref") != ref
      or type(response.get("object")) is not dict
      or response["object"].get("type") != "commit"):
    raise SubmissionError("submission receipt ref malformed")
  sha = response["object"].get("sha")
  if type(sha) is not str or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SubmissionError("submission receipt commit malformed")
  try:
    commit = backend.get("git/commits/" + sha)
    if type(commit) is not dict or commit.get("sha") != sha:
      raise SubmissionError("submission receipt object differs")
    record = decode_submission(commit.get("message"), repository=backend.repository, guid=guid)
    parents = commit.get("parents")
    if (type(parents) is not list or len(parents) != 1
        or type(parents[0]) is not dict or parents[0].get("sha") != record["candidate_sha"]):
      raise SubmissionError("submission receipt does not bind its candidate")
    candidate = backend.get("git/commits/" + record["candidate_sha"])
    if (type(candidate) is not dict or candidate.get("sha") != record["candidate_sha"]
        or type(candidate.get("tree")) is not dict
        or type(commit.get("tree")) is not dict
        or type(candidate["tree"].get("sha")) is not str
        or re.fullmatch(r"[0-9a-f]{40}", candidate["tree"]["sha"]) is None
        or commit["tree"].get("sha") != candidate["tree"].get("sha")):
      raise SubmissionError("submission receipt changes candidate inputs")
    comparison = backend.get("compare/" + record["parent_sha"] + "..." + record["candidate_sha"])
    if (type(comparison) is not dict or type(comparison.get("merge_base_commit")) is not dict
        or comparison["merge_base_commit"].get("sha") != record["parent_sha"]):
      raise SubmissionError("submission historical parent is not candidate ancestry")
    if backend.get("git/ref/" + ref.removeprefix("refs/")) != response:
      raise SubmissionError("submission receipt moved during read")
  except SubmissionError:
    raise
  except Exception as error:
    raise SubmissionError("submission provenance read UNKNOWN") from error
  return record
