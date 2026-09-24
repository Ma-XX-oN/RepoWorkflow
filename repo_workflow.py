#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from repo_workflow.actions_policy import ActionsPolicyError, check_actions_policy
from repo_workflow.artifacts import (
  ArtifactError,
  ArtifactResult,
  commit_artifact_changes,
  materialize_artifacts,
  write_artifact_result,
)
from repo_workflow.branch_policy import BranchPolicyError, check_branch_policy
from repo_workflow.config import ConfigError, load_config
from repo_workflow.git import (
  GitError,
  changed_files,
  head_sha,
  repository_state,
  restore_repository_state,
)
from repo_workflow.github_adapter import (
  AdapterError,
  github_matrix,
  github_prepare_context,
  github_prepare_runner,
  load_github_config,
  request_changed,
)
from repo_workflow.guard import GuardError, validate_candidate
from repo_workflow.local import verify_local
from repo_workflow.repository_policy import (
  RepositoryPolicyError,
  check_repository_policy,
)
from repo_workflow.results import (
  ResultError,
  finalize_results,
  run_environment,
)


ENGINE_ROOT = Path(__file__).resolve().parent


def _root(value: str) -> Path:
  return Path(value).resolve()


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Shared repository workflow engine")
  parser.add_argument("--root", default=".", help="consumer repository root")
  commands = parser.add_subparsers(dest="command", required=True)

  preflight = commands.add_parser("preflight")
  preflight.add_argument("--expected-sha")

  commands.add_parser("matrix")

  verify = commands.add_parser("verify")
  verify.add_argument("--tag", action="store_true")
  verify.add_argument("--push", action="store_true")

  run = commands.add_parser("run")
  run.add_argument("--environment", required=True)
  run.add_argument("--result", required=True)
  run.add_argument("--expected-sha")

  finalize = commands.add_parser("finalize")
  finalize.add_argument("--results-dir", required=True)
  finalize.add_argument("--expected-sha")
  finalize.add_argument("--tag", action="store_true")
  finalize.add_argument("--push", action="store_true")

  branch = commands.add_parser("branch-policy")
  branch.add_argument("--branch", required=True)
  branch.add_argument("--pr-base")
  branch.add_argument("--remote")

  actions = commands.add_parser("actions-policy")
  actions.add_argument("--engine-root", default=str(ENGINE_ROOT))

  repository = commands.add_parser("repository-policy")
  repository.add_argument("--engine-root", default=str(ENGINE_ROOT))

  materialize = commands.add_parser("materialize-artifacts")
  materialize.add_argument("--result")
  materialize.add_argument("--commit", action="store_true")

  github_request = commands.add_parser("github-request")
  github_request.add_argument("--event-name", required=True)
  github_request.add_argument("--event-path", required=True)

  commands.add_parser("github-matrix")
  commands.add_parser("github-prepare-runner")
  commands.add_parser("github-prepare-context")
  return parser


def main() -> int:
  args = build_parser().parse_args()
  root = _root(args.root)
  try:
    if args.command == "preflight":
      candidate = validate_candidate(
        root,
        load_config(root),
        expected_sha=args.expected_sha,
      )
      print(json.dumps({"version": candidate.version, "commit": candidate.commit}))
      return 0

    if args.command == "matrix":
      config = load_config(root)
      print(json.dumps({"include": [
        {
          "id": env["id"],
          "required": bool(env.get("required", True)),
          "platform": env.get("platform", "any"),
          "capabilities": list(env.get("capabilities", [])),
        }
        for env in config["environments"]
      ]}, separators=(",", ":")))
      return 0

    if args.command == "verify":
      outcome = verify_local(
        root,
        engine_root=ENGINE_ROOT,
        do_tag=args.tag,
        push=args.push,
      )
      return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]

    if args.command == "run":
      return run_environment(
        root,
        load_config(root),
        args.environment,
        Path(args.result),
        expected_sha=args.expected_sha,
      )

    if args.command == "finalize":
      outcome = finalize_results(
        root,
        Path(args.results_dir),
        do_tag=args.tag,
        push=args.push,
        expected_sha=args.expected_sha,
      )
      return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]

    if args.command == "branch-policy":
      config = load_config(root)
      remote = args.remote or config["repository"]["authoritativeRemote"]
      check_branch_policy(root, args.branch, args.pr_base or None, remote)
      print(f"Branch policy passed: {args.branch}")
      return 0

    if args.command == "actions-policy":
      check_actions_policy(root, Path(args.engine_root).resolve())
      print("Actions policy passed")
      return 0

    if args.command == "repository-policy":
      check_repository_policy(root, Path(args.engine_root).resolve())
      print("Repository policy passed")
      return 0

    if args.command == "materialize-artifacts":
      config = load_config(root)
      candidate = validate_candidate(root, config)
      before_state = repository_state(root)
      try:
        result = materialize_artifacts(root, config)
      except ArtifactError as exc:
        result = ArtifactResult("FAIL", changed_files(root), [str(exc)])
      commit = head_sha(root)
      if result.status == "PASS" and args.commit:
        commit = commit_artifact_changes(
          root,
          result,
          f"chore(workflow): materialize generated artifacts for {candidate.version}",
        )
      elif result.status != "PASS":
        restore_repository_state(root, before_state)
        commit = before_state.commit
      if args.result:
        write_artifact_result(
          Path(args.result),
          result,
          version=candidate.version,
          commit=commit,
        )
      if result.status != "PASS":
        for failure in result.failures:
          print(f"WARNING: {failure}", file=sys.stderr)
        return 2 if result.status == "INCOMPLETE" else 1
      if args.commit:
        print(json.dumps({"commit": commit, "changedFiles": result.changed_files}))
      else:
        print(json.dumps({"changedFiles": result.changed_files}))
      return 0

    if args.command == "github-request":
      value = request_changed(root, args.event_name, Path(args.event_path))
      print("true" if value else "false")
      return 0

    if args.command == "github-matrix":
      print(json.dumps(
        github_matrix(load_config(root), load_github_config(root)),
        separators=(",", ":"),
      ))
      return 0

    if args.command == "github-prepare-runner":
      print(github_prepare_runner(load_github_config(root)))
      return 0

    if args.command == "github-prepare-context":
      print(json.dumps(
        github_prepare_context(load_config(root), load_github_config(root)),
        separators=(",", ":"),
      ))
      return 0
  except (
    ActionsPolicyError,
    AdapterError,
    ArtifactError,
    BranchPolicyError,
    ConfigError,
    RepositoryPolicyError,
    ResultError,
    GitError,
    GuardError,
    ValueError,
  ) as exc:
    print(f"RepoWorkflow error: {exc}", file=sys.stderr)
    return 2
  raise AssertionError("unreachable")


if __name__ == "__main__":
  raise SystemExit(main())
