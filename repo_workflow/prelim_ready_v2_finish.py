"""Finalize a local destination-qualified candidate without publishing READY."""
from .git import git
from .prelim_attempt import _local_ref, _sha
from .prelim_attempt_lock import PrelimError, _workspace
from .prelim_ready_v2_record import (
  preparation_ref, prepared_snapshot, validate_preparation,
)
from .version_adapter import read_version


def complete_prepared_candidate(root, store, record, config, writer):
  value = record["value"]
  validate_preparation(value)
  guid = value["guid"]
  workspace = _workspace(root, "v2-" + guid)
  if not workspace.is_dir():
    raise PrelimError("prepared candidate workspace missing")
  if git(workspace, "ls-files", "-u").stdout.strip():
    raise PrelimError("unresolved prepared candidate conflicts")
  if read_version(workspace, config) != value["proposed_version"]:
    raise PrelimError("prepared candidate version changed")
  merging = git(workspace, "rev-parse", "MERGE_HEAD", check=False).returncode == 0
  if merging:
    git(workspace, "add", "-u")
    git(workspace, "diff", "--cached", "--check")
    git(workspace, "commit", "-m", "Prepare qualified candidate " + guid)
  else:
    message = git(workspace, "log", "-1", "--format=%s").stdout.strip()
    if message != "Prepare qualified candidate " + guid:
      no_merge = (
        message == "PRELIM proposed version " + value["proposed_version"]
        and git(workspace, "merge-base", "--is-ancestor",
                value["source_sha"], "HEAD", check=False).returncode == 0
      )
      if not no_merge:
        raise PrelimError("accepted source not present in prepared candidate")
    if git(workspace, "status", "--porcelain").stdout.strip():
      raise PrelimError("prepared workspace changed during construction")
  candidate = _sha(git(workspace, "rev-parse", "HEAD").stdout.strip(),
                   "candidate")
  for ancestor in (value["base_sha"], value["source_sha"]):
    if git(workspace, "merge-base", "--is-ancestor", ancestor, candidate,
           check=False).returncode:
      raise PrelimError("candidate missing accepted source or parent")
  ref = preparation_ref(guid)
  prior = _local_ref(root, ref)
  if prior is None:
    git(root, "update-ref", ref, candidate, "0" * 40)
  elif prior != candidate:
    raise PrelimError("prepared local candidate identity changed")
  record = store.replace(
    record["key"], record["revision"],
    {**value, "state": "constructed", "candidate_sha": candidate}, writer,
  )
  git(root, "worktree", "remove", str(workspace))
  return prepared_snapshot(record["value"])
