"""Default native done dispatch for local submission and the ordinary CI worker."""
from dataclasses import dataclass
import os
from pathlib import Path

from .config import load_config
from .done_results import publish_report
from .done_submission import DoneSubmissionError, SubmittedDone
from .done_workflow import completed_submission, dispatch_done, prepare_done
from .git import changed_files, current_branch
from .parent_branch import ParentBranchError, recover_parent_branch
from .source_tip import source_tip
from .testing_identity import testing_issue


@dataclass(frozen=True)
class FunctionalDone:
  """Actual functional workflow disposition; no external verifier claim."""
  value: dict


def execute_native_done(root: Path, release: str, *, engine_root: Path):
  """Submit locally, or request the platform worker during a hosted invocation.

  Parameters
  ----------
  root : Path
      Issue checkout.
  release : str
      Requested patch, minor or major integration policy.
  engine_root : Path
      Installed RepoWorkflow checkout.

  Returns
  -------
  SubmittedDone or FunctionalDone
      Verified submission or actual recorded worker disposition.
  """
  root = Path(root).resolve()
  config = load_config(root) if (root / ".ci/repoworkflow.json").is_file() else None
  remote = config["repository"]["authoritativeRemote"] if config else "origin"
  hosted = os.environ.get("RWF_HOSTED_INVOCATION") == "1"
  try:
    recover_parent_branch(root, current_branch(root))
  except ParentBranchError:
    prior = None
  else:
    issue = testing_issue(root)
    prior = completed_submission(root, issue, remote)
  if prior is not None and not changed_files(root) and source_tip(root) in {
      prior["source_sha"], prior["candidate_sha"]}:
    return FunctionalDone(prior)
  try:
    from .done_submission import submit_done
    submitted = submit_done(root, release, engine_root=engine_root)
  except DoneSubmissionError as error:
    if not hosted or error.submission is None or "durable handoff:" not in str(error):
      raise
    from .done_conflict import record_conflict
    return FunctionalDone(record_conflict(root, error.submission, str(error)))
  plan = prepare_done(root, submitted.ready.ref, engine_root=engine_root, remote=remote)
  if plan["status"] != "prepared":
    return FunctionalDone(plan)
  if source_tip(root) == plan["candidate_sha"]:
    publish_report(root, plan)
  if hosted:
    return FunctionalDone(dispatch_done(root, plan))
  return submitted
