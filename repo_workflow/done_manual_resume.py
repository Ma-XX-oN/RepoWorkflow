"""Publish an external tester's verdict and resume its pending PRELIM worker."""
import json
from pathlib import Path

from .config import load_config
from .done_results import publish_report
from .git import git
from .prelim_queue import discover_ready_prelims, latest_prelims
from .prelim_submission import PREFIX, decode_submission, submission_ref


class ManualReportDeliveryError(RuntimeError):
  """A saved verdict could not wake its submitted CI attempt."""


def resume_manual_done(root: Path, issue: int, candidate: str, *, complete: bool) -> dict | None:
  """Deliver actual manual evidence for the latest matching submission.

  Parameters
  ----------
  root : Path
      Tester checkout, on any branch containing the candidate.
  issue : int
      Issue whose verdict was recorded.
  candidate : str
      Exact effective source tested.
  complete : bool
      All manual cases passed, or a recorded failure stopped testing.

  Returns
  -------
  dict or None
      Reported/submitted disposition, or None when no matching submission exists.
  """
  config = load_config(root) if (root / ".ci/repoworkflow.json").is_file() else None
  remote = config["repository"]["authoritativeRemote"] if config else "origin"
  if git(root, "remote", "get-url", remote, check=False).returncode:
    return None  # Standalone manual testing has no submitted CI attempt to resume.
  observed = git(root, "ls-remote", "--heads", remote, f"refs/heads/PRELIM-issue-{issue}.*")
  refs = {line.split("\t")[1]: line.split("\t")[0] for line in observed.stdout.splitlines()}
  selected = latest_prelims(discover_ready_prelims(refs))
  if not selected or selected[0].sha != candidate:
    return None  # Results for an older submission never wake a newer candidate.
  ready = selected[0]
  git(root, "fetch", "--no-tags", remote, submission_ref(ready.guid))
  message = git(root, "show", "-s", "--format=%B", "FETCH_HEAD").stdout.rstrip("\n")
  repository = json.loads(message.removeprefix(PREFIX))["repository"]
  saved = decode_submission(message, repository=repository, guid=ready.guid)
  if saved["candidate_sha"] != candidate or saved["prelim_ref"] != ready.ref:
    raise ValueError("manual result differs from selected submission")
  plan = {**saved, "issue": issue, "remote": remote, "version_suffix": ready.version}
  report = publish_report(root, plan)
  if complete:
    from .done_workflow import dispatch_done
    from adapters.repo_host_github_provider import ProviderError
    try:
      return dispatch_done(root, plan)
    except ProviderError as error:
      raise ManualReportDeliveryError("CI dispatch pending for recorded manual verdict") from error
  return {"status": "reported", "report_ref": report, "prelim_ref": ready.ref}
