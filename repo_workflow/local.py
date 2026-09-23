from __future__ import annotations

from pathlib import Path
import tempfile

from .artifacts import (
  ArtifactError,
  ArtifactResult,
  commit_artifact_changes,
  materialize_artifacts,
  write_artifact_result,
)
from .branch_policy import check_branch_policy
from .config import load_config
from .git import (
  changed_files,
  current_branch,
  git,
  repository_state,
  restore_repository_state,
)
from .guard import validate_candidate
from .repository_policy import check_repository_policy
from .results import ResultError, finalize_results, run_environment


def verify_local(
  root: Path,
  *,
  engine_root: Path,
  do_tag: bool = False,
  push: bool = False,
) -> str:
  if push and not do_tag:
    raise ResultError("push requires tag creation")
  root = root.resolve()
  engine_root = engine_root.resolve()
  check_repository_policy(root, engine_root)
  config = load_config(root)
  branch = current_branch(root)
  if branch == "HEAD":
    raise ValueError("local authoritative verification requires a named branch")
  remote = config["repository"]["authoritativeRemote"]
  check_branch_policy(root, branch, None, remote)
  candidate = validate_candidate(root, config)

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
      candidate = validate_candidate(root, config, expected_sha=commit)
      if push and commit != before_state.commit:
        git(root, "push", remote, f"HEAD:{branch}")
    else:
      restore_repository_state(root, before_state)

    write_artifact_result(
      results_dir / "artifacts.json",
      artifact_result,
      version=candidate.version,
      commit=candidate.commit,
    )

    for environment in config["environments"]:
      run_environment(
        root,
        config,
        environment["id"],
        results_dir / f"{environment['id']}.json",
        expected_sha=candidate.commit,
      )
    return finalize_results(
      root,
      results_dir,
      do_tag=do_tag,
      push=push,
      expected_sha=candidate.commit,
    )
