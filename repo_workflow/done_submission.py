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
from .prelim_queue import discover_ready_prelims, latest_prelims, parse_ready_prelim, prelim_ref_for_version
from .prelim_submission import decode_submission, publish_submission, submission_ref
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


def prepare_submission_candidate(root, source, parent_sha, config, issue, engine_root,
                                 *, parent_reintegration=True):
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
  parent_reintegration : bool
      Whether reconstruction retains an already prepared implementation.
      A newly prepared implementation keeps its new Q and R=0.

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
  parents = git(workspace, "rev-list", "--parents", "-n", "1", source_tip(workspace)).stdout.split()
  needs_reintegration = (not at_tip and parent_reintegration
                         and len(parents) == 3 and parents[1:] == [parent_sha, source])
  version = _prepare_version(workspace, engine_root, config, issue,
                             parent_reintegration=needs_reintegration)
  return source_tip(workspace), version


def _prepare_version(root, engine_root, config, issue, *, parent_reintegration=False):
  """Prepare repository-owned version state once per changed source.

  Parameters
  ----------
  root, engine_root : Path
      Candidate checkout and installed engine.
  config : dict or None
      Consumer configuration, or None for engine self-testing.
  issue : int
      Owning issue.
  parent_reintegration : bool
      Advance R for a newly reconstructed parent candidate, without advancing Q.

  Returns
  -------
  str
      Committed development version to use for this candidate.
  """
  if config is None:
    from .engine_remote import prepare_engine_request
    return prepare_engine_request(root, stage="regression", issue=issue,
                                   parent_reintegration=parent_reintegration)
  from .candidate import prepare_development_candidate
  candidate, _ = prepare_development_candidate(root, config,
                                               parent_reintegration=parent_reintegration)
  return candidate.version


def _latest_submission(root, remote, issue, repository):
  """Read the latest physical PRELIM and its immutable provenance.

  Parameters
  ----------
  root : Path
      Repository checkout.
  remote, repository : str
      Configured provider and repository identity.
  issue : int
      Owning issue.

  Returns
  -------
  dict or None
      Latest submission, independent of test outcome.
  """
  raw = git(root, "ls-remote", "--heads", remote, f"refs/heads/PRELIM-issue-{issue}.*").stdout
  refs = {line.split()[1]: line.split()[0] for line in raw.splitlines()}
  latest = latest_prelims(discover_ready_prelims(refs))
  if not latest:
    return None
  ready = latest[0]
  git(root, "fetch", "--no-tags", remote, ready.ref)
  git(root, "fetch", "--no-tags", remote, submission_ref(ready.guid))
  message = git(root, "show", "-s", "--format=%B", "FETCH_HEAD").stdout.rstrip("\n")
  return decode_submission(message, repository=repository, guid=ready.guid)


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
        from .done_manual_resume import resume_manual_done, ManualReportDeliveryError
        from .git import GitError
        try:
          resume_manual_done(root, issue, material, complete=True)
        except (GitError, ManualReportDeliveryError):
          raise DoneSubmissionError("current source has a failed test; CI delivery pending; repair before done")
        raise DoneSubmissionError("current source has a failed test; repair before done")
    commit_owned_files(root, [relative], "test: record completion evidence")
  dirty = changed_files(root)
  if dirty:
    raise DoneSubmissionError("commit source changes before done: " + ", ".join(dirty))
  if config is None:
    from .engine_version_adapter import read_engine_version
    before_version = read_engine_version(root)
  else:
    from .version_adapter import read_version
    before_version = read_version(root, config)
  version = _prepare_version(root, engine_root, config, issue)
  new_implementation = version != before_version
  source = source_tip(root)
  latest = _latest_submission(root, remote, issue, info["repository"])
  integration_source = source
  if latest is not None and latest["source_sha"] == source:
    integration_source = latest["candidate_sha"]
  parent_ref = "refs/heads/" + parent
  observed = git(root, "ls-remote", "--heads", remote, parent_ref).stdout.split()
  if (len(observed) != 2 or observed[1] != parent_ref
      or re.fullmatch(r"[0-9a-f]{40}", observed[0]) is None):
    raise DoneSubmissionError("authoritative parent tip unavailable")
  parent_sha = observed[0]
  git(root, "fetch", "--no-tags", remote, parent_ref)
  try:
    candidate, version = prepare_submission_candidate(
      root, integration_source, parent_sha, config, issue, engine_root,
      parent_reintegration=not new_implementation)
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
