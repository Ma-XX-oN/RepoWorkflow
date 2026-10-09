from __future__ import annotations

from pathlib import Path
from typing import Callable
import tempfile

from .artifacts import (
  ArtifactError,
  ArtifactResult,
  commit_artifact_changes,
  materialize_artifacts,
  write_artifact_result,
)
from .branch_policy import check_branch_policy
from .candidate import prepare_development_candidate
from .config import load_config
from .git import (
  changed_files,
  current_branch,
  git,
  repository_state,
  restore_repository_state,
)
from .guard import validate_candidate, validate_stable_candidate
from .repository_policy import check_repository_policy
from .results import (
  assert_terminal_tag_available,
  finalize_results,
  finalize_stable_results,
  run_environment,
  run_stable_environment,
)


def _verify_local(
  root: Path,
  *,
  engine_root: Path,
  stable: bool,
  do_tag: bool,
  push: bool,
  candidate_observer: Callable[[str], None] | None = None,
) -> str:
  root = root.resolve()
  engine_root = engine_root.resolve()
  transaction_state = repository_state(root)
  try:
    check_repository_policy(root, engine_root)
    config = load_config(root)
    branch = current_branch(root)
    if branch == "HEAD":
      raise ValueError("local authoritative verification requires a named branch")
    remote = config["repository"]["authoritativeRemote"]
    check_branch_policy(root, branch, None, remote)
    if stable:
      candidate = validate_stable_candidate(root)
    else:
      candidate, _prepared = prepare_development_candidate(
        root,
        config,
        push=False,
      )
  except Exception:
    restore_repository_state(root, transaction_state)
    raise

  with tempfile.TemporaryDirectory(prefix="repoworkflow-results-") as directory:
    results_dir = Path(directory)
    before_state = repository_state(root)
    try:
      artifact_result = materialize_artifacts(root, config)
    except ArtifactError as exc:
      artifact_result = ArtifactResult("FAIL", changed_files(root), [str(exc)])

    if artifact_result.status == "PASS":
      commit = commit_artifact_changes(
        root,
        artifact_result,
        f"chore(workflow): materialize generated artifacts for {candidate.version}",
      )
      if stable and push and commit != before_state.commit:
        git(root, "push", remote, f"HEAD:{branch}")
      candidate = (
        validate_stable_candidate(root, expected_sha=commit)
        if stable
        else validate_candidate(root, config, expected_sha=commit)
      )
    else:
      restore_repository_state(root, before_state)

    write_artifact_result(
      results_dir / "artifacts.json",
      artifact_result,
      version=candidate.version,
      commit=candidate.commit,
    )

    if candidate_observer is not None:
      candidate_observer(candidate.commit)

    for environment in config["environments"]:
      runner = run_stable_environment if stable else run_environment
      runner(
        root,
        config,
        environment["id"],
        results_dir / f"{environment['id']}.json",
        expected_sha=candidate.commit,
      )
    finalizer = finalize_stable_results if stable else finalize_results
    try:
      return finalizer(
        root,
        results_dir,
        do_tag=do_tag,
        push=push if stable else False,
        expected_sha=candidate.commit,
      )
    except Exception:
      if not stable:
        restore_repository_state(root, transaction_state)
      raise


def verify_local(
  root: Path,
  *,
  engine_root: Path,
  push: bool = False,
  candidate_observer: Callable[[str], None] | None = None,
) -> str:
  root = root.resolve()
  before = repository_state(root)
  try:
    outcome = _verify_local(
      root,
      engine_root=engine_root,
      stable=False,
      do_tag=not push,
      push=push,
      candidate_observer=candidate_observer,
    )
    if push and outcome != "INCOMPLETE":
      config = load_config(root)
      branch = current_branch(root)
      remote = config["repository"]["authoritativeRemote"]
      candidate = validate_candidate(root, config)
      tag = (
        f"v{candidate.version}"
        if outcome == "PASS"
        else f"v{candidate.version}-CI-FAIL"
      )
      assert_terminal_tag_available(root, candidate, tag, push=True)
      git(root, "tag", "-a", tag, candidate.commit, "-m", tag)
      # Publish the candidate branch and immutable terminal result as one remote transaction.
      git(root, "push", "--atomic", remote, f"HEAD:{branch}", f"refs/tags/{tag}")
  except Exception:
    restore_repository_state(root, before)
    raise
  return outcome


def verify_stable_local(
  root: Path,
  *,
  engine_root: Path,
  do_tag: bool = False,
  push: bool = False,
) -> str:
  return _verify_local(
    root,
    engine_root=engine_root,
    stable=True,
    do_tag=do_tag,
    push=push,
  )
