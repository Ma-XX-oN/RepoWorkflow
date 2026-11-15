"""Prepare and publish a versioned completion submission without merge authority."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .config import load_config
from .git import changed_files, current_branch, git
from .owned_commit import commit_owned_files
from .parent_branch import recover_parent_branch
from .prelim_queue import parse_ready_prelim, prelim_ref_for_version
from .prelim_submission import publish_submission
from .repo_info_adapter import repository_info, resolve_info_config
from .source_tip import source_tip
from .test_results_reader import parse_testing_log
from .testing_identity import testing_issue


class DoneSubmissionError(ValueError):
  """Source, version, parent or completion submission could not be established."""
  submission: dict | None = None


@dataclass(frozen=True)
class SubmittedDone:
  ready: object
  version: str
  parent_sha: str
  release: str


def prepare_submission_candidate(root, source, parent_sha, config, issue, engine_root):
  """Copy stale source to the parent and prepare its version before testing.

  Parameters
  ----------
  root, engine_root : Path
      Repository containing the source and installed engine.
  source, parent_sha : str
      Exact material source and independently observed parent tip.
  config : dict or None
      Repository-owned version adapter configuration.
  issue : int
      Owning issue.

  Returns
  -------
  tuple of str
      Prepared candidate SHA and its full development version. A stable
      detached construction checkout permits unchanged resumes; callers
      may run tests on any checkout containing the same effective candidate.
  """
  at_tip = git(root, "merge-base", "--is-ancestor", parent_sha, source, check=False).returncode == 0
  if at_tip and source_tip(root) == source:
    version = _prepare_version(root, engine_root, config, issue)
    return source_tip(root), version
  common = Path(git(root, "rev-parse", "--git-common-dir").stdout.strip())
  if not common.is_absolute():
    common = root / common
  workspace = common.resolve() / "rwf-done-candidates" / f"{issue}-{source}-{parent_sha}"
  if at_tip and not workspace.exists():
    workspace.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", str(workspace), source)
  if not workspace.exists():
    merged = git(root, "merge-tree", "--write-tree", parent_sha, source, check=False)
    if merged.returncode:
      from .invocation_identity import ensure_public_runtime_identity
      from .state_store import durable_store, StateStoreError
      writer = ensure_public_runtime_identity(root)
      store = durable_store(root)
      key = f"issues/{issue}/done-conflicts/{source}-{parent_sha}"
      value = {"source_sha":source,"parent_sha":parent_sha,
               "merge_output":merged.stdout,"diagnostic":merged.stderr}
      try:
        store.create(key, value, writer)
      except StateStoreError:
        if store.read(key)["value"] != value:
          raise DoneSubmissionError("conflict handoff differs; reconcile durable state")
      raise DoneSubmissionError("source conflicts with parent; durable handoff: " + key)
    tree = merged.stdout.split("\n", 1)[0]
    if re.fullmatch(r"[0-9a-f]{40}", tree) is None:
      raise DoneSubmissionError("parent reconstruction returned no exact tree")
    candidate = git(root, "commit-tree", tree, "-p", parent_sha, "-p", source,
                    "-m", f"Integrate issue {issue} onto parent {parent_sha}").stdout.strip()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", str(workspace), candidate)
  if changed_files(workspace):
    raise DoneSubmissionError("prepared candidate has changed inputs; reconcile before resuming")
  version = _prepare_version(workspace, engine_root, config, issue)
  return source_tip(workspace), version


def _prepare_version(root, engine_root, config, issue):
  """Prepare repository-owned version state once per changed source.

  Parameters
  ----------
  root, engine_root : Path
      Candidate checkout and installed engine.
  config : dict or None
      Consumer configuration, or None for engine self-testing.
  issue : int
      Owning issue.

  Returns
  -------
  str
      Committed development version to use for this candidate.
  """
  if config is None:
    from .engine_remote import prepare_engine_request
    return prepare_engine_request(root, stage="regression", issue=issue)
  from .candidate import prepare_development_candidate
  candidate, _ = prepare_development_candidate(root, config)
  return candidate.version


def submit_done(root: Path, release: str, *, engine_root: Path) -> SubmittedDone:
  """Publish exact source/parent identity while allowing deferred tests.

  Parameters
  ----------
  root : Path
      Issue checkout with a permanent authoritative parent identity.
  release : str
      Requested patch, minor or major integration policy.
  engine_root : Path
      Installed engine checkout.

  Returns
  -------
  SubmittedDone
      Exact physical submission after provider readback. This result does
      not report a parent merge, test PASS, or completed issue lifecycle.
  """
  root, engine_root = Path(root).resolve(), Path(engine_root).resolve()
  if release not in {"patch", "minor", "major"}:
    raise DoneSubmissionError("done requires patch, minor, or major")
  config = load_config(root) if (root / ".ci/repoworkflow.json").is_file() else None
  if config is None and root != engine_root:
    raise DoneSubmissionError("consumer completion requires repository configuration")
  issue = testing_issue(root)
  branch = current_branch(root)
  parent = recover_parent_branch(root, branch)
  remote = config["repository"]["authoritativeRemote"] if config else "origin"
  info = repository_info(root, resolve_info_config(root, config))
  material = source_tip(root)
  relative = f".repoworkflow/validation/testResults-{issue}.jsonl"
  log = root / relative
  if log.exists():
    if log.is_symlink():
      raise DoneSubmissionError("completion testing log cannot be a symlink")
    for result in parse_testing_log(log.read_text(encoding="utf-8")):
      if result["result"] == "failed" and source_tip(root, result["testSHA"]) == material:
        raise DoneSubmissionError("current source has a failed test; repair before done")
    commit_owned_files(root, [relative], "test: record completion evidence")
  dirty = changed_files(root)
  if dirty:
    raise DoneSubmissionError("commit source changes before done: " + ", ".join(dirty))
  version = _prepare_version(root, engine_root, config, issue)
  source = source_tip(root)
  parent_ref = "refs/heads/" + parent
  observed = git(root, "ls-remote", "--heads", remote, parent_ref).stdout.split()
  if (len(observed) != 2 or observed[1] != parent_ref
      or re.fullmatch(r"[0-9a-f]{40}", observed[0]) is None):
    raise DoneSubmissionError("authoritative parent tip unavailable")
  parent_sha = observed[0]
  git(root, "fetch", "--no-tags", remote, parent_ref)
  try:
    candidate, version = prepare_submission_candidate(
      root, source, parent_sha, config, issue, engine_root)
  except DoneSubmissionError as error:
    error.submission = {"issue": issue, "remote": remote, "repository": info["repository"],
      "source_sha": source, "candidate_sha": source, "parent_sha": parent_sha,
      "destination": parent, "prelim_ref": prelim_ref_for_version(version), "release": release}
    raise
  ref = prelim_ref_for_version(version)
  ready = parse_ready_prelim(ref, candidate, destination=parent)
  inputs = json.dumps({"tree":git(root, "rev-parse", candidate + "^{tree}").stdout.strip(),
                      "parent":parent_sha,"release":release}, sort_keys=True).encode("utf-8")
  record = {"repository":info["repository"],"guid":ready.guid,"prelim_ref":ref,
            "source_sha":source,"candidate_sha":candidate,"parent_sha":parent_sha,
            "destination":parent,"version":version,"release":release,
            "inputs_sha256":hashlib.sha256(inputs).hexdigest()}
  published = publish_submission(root, record, remote=remote)
  return SubmittedDone(published, version, parent_sha, release)
