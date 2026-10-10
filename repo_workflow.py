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
from repo_workflow.classification import (
  ClassificationError,
  changed_paths,
  classify_paths,
  load_change_classes,
)
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
  github_mode,
  github_prepare_context,
  github_prepare_runner,
  load_github_config,
  request_changed,
)
from repo_workflow.guard import (
  GuardError,
  validate_candidate,
  validate_stable_candidate,
)
from repo_workflow.local import verify_local, verify_stable_local
from repo_workflow.public_cli import (
  handle_completion,
  handle_help,
  handle_public,
  is_public_command,
)
from repo_workflow.current_work_store import CurrentWorkError
from repo_workflow.high_risk import HighRiskError
from repo_workflow.lifecycle_store import LifecycleError
from repo_workflow.test_catalogue import TestCatalogueError
from repo_workflow.dependency_sync import DependencySyncConflict
from repo_workflow.issue_metadata import IssueMetadataError
from repo_workflow.lane_list import LaneListError
from repo_workflow.lane_selection import LaneSelectionError
from repo_workflow.lane_render import LaneRenderError
from repo_workflow.repo_info_adapter import RepoInfoError
from repo_workflow.repo_ci_dispatcher import (
  RepoCiError, OPERATIONS, dispatch, error_envelope,
)
from repo_workflow.relationship_store import RelationshipStoreError
from repo_workflow.runtime_identity import RuntimeIdentityError
from repo_workflow.state_store import StateStoreError
from repo_workflow.ticket_dependency_adapter import TicketDependencyError
from repo_workflow.repository_policy import (
  RepositoryPolicyError,
  check_repository_policy,
)
from repo_workflow.results import (
  ResultError,
  finalize_results,
  finalize_stable_results,
  run_environment,
  run_stable_environment,
)
from repo_workflow.version_adapter import VersionAdapterError
from repo_workflow.workspace_cli import WorkspaceCommandError
from repo_workflow.workspace_store import WorkspaceClaimError
from repo_workflow.workspace_worktree import WorktreeError


ENGINE_ROOT = Path(__file__).resolve().parent


def _root(value: str) -> Path:
  return Path(value).resolve()


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Shared repository workflow engine")
  parser.add_argument("--root", default=".", help="consumer repository root")
  commands = parser.add_subparsers(dest="command", required=True)

  repo_ci = commands.add_parser("repo-ci")
  repo_ci.add_argument("operation", choices=sorted(OPERATIONS))

  preflight = commands.add_parser("preflight")
  preflight.add_argument("--expected-sha")

  stable_preflight = commands.add_parser("stable-preflight")
  stable_preflight.add_argument("--expected-sha")

  commands.add_parser("matrix")

  classify = commands.add_parser("classify")
  classify.add_argument("--base", required=True)
  classify.add_argument("--head", default="HEAD")

  verify = commands.add_parser("verify")
  verify.add_argument("--tag", action="store_true", help=argparse.SUPPRESS)
  verify.add_argument("--push", action="store_true")

  verify_stable = commands.add_parser("verify-stable")
  verify_stable.add_argument("--tag", action="store_true")
  verify_stable.add_argument("--push", action="store_true")

  run = commands.add_parser("run")
  run.add_argument("--environment", required=True)
  run.add_argument("--result", required=True)
  run.add_argument("--expected-sha")

  stable_run = commands.add_parser("stable-run")
  stable_run.add_argument("--environment", required=True)
  stable_run.add_argument("--result", required=True)
  stable_run.add_argument("--expected-sha")

  finalize = commands.add_parser("finalize")
  finalize.add_argument("--results-dir", required=True)
  finalize.add_argument("--expected-sha")
  finalize.add_argument("--tag", action="store_true")
  finalize.add_argument("--push", action="store_true")

  stable_finalize = commands.add_parser("stable-finalize")
  stable_finalize.add_argument("--results-dir", required=True)
  stable_finalize.add_argument("--expected-sha")
  stable_finalize.add_argument("--tag", action="store_true")
  stable_finalize.add_argument("--push", action="store_true")

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
  materialize.add_argument("--stable", action="store_true")

  github_request = commands.add_parser("github-request")
  github_request.add_argument("--event-name", required=True)
  github_request.add_argument("--event-path", required=True)

  github_mode_parser = commands.add_parser("github-mode")
  github_mode_parser.add_argument("--event-name", required=True)
  github_mode_parser.add_argument("--event-path", required=True)
  github_mode_parser.add_argument("--branch", required=True)

  commands.add_parser("github-matrix")
  commands.add_parser("github-prepare-runner")
  commands.add_parser("github-prepare-context")
  return parser


def _subcommand_names(parser: argparse.ArgumentParser) -> set[str]:
  for action in parser._actions:
    if isinstance(action, argparse._SubParsersAction):
      return set(action.choices)
  return set()


def _public_route(argv: list[str]) -> tuple[str, Path, list[str], bool] | None:
  pre_parser = argparse.ArgumentParser(add_help=False)
  pre_parser.add_argument("--root", default=".")
  pre_args, words = pre_parser.parse_known_args(argv)
  if not words:
    return None

  root = _root(pre_args.root)
  if words[0] in {"-h", "--help"}:
    return "help", root, [], False

  if words[0] == "complete":
    completion_words = words[1:]
    describe = False
    if completion_words and completion_words[0] == "--describe":
      describe = True
      completion_words = completion_words[1:]
    if completion_words and completion_words[0] == "--":
      completion_words = completion_words[1:]
    return "complete", root, completion_words, describe

  parser = build_parser()
  if is_public_command(words[0]):
    if words[-1] in {"-h", "--help"}:
      return "help", root, words[:-1], False
    return "public", root, words, False
  if words[0] not in _subcommand_names(parser):
    return "public", root, words, False
  return None


def main(argv: list[str] | None = None) -> int:
  argv = list(sys.argv[1:] if argv is None else argv)
  try:
    routed = _public_route(argv)
    if routed is not None:
      mode, root, words, describe = routed
      if mode == "complete":
        return handle_completion(root, words, describe=describe)
      if mode == "help":
        return handle_help(root, words)
      return handle_public(root, words, engine_root=ENGINE_ROOT)

    args = build_parser().parse_args(argv)
    root = _root(args.root)
    if args.command == "repo-ci":
      raw = sys.stdin.buffer.read()
      try:
        value = dispatch(root, args.operation, raw)
      except RepoCiError as exc:
        error = error_envelope(raw, args.operation, exc)
        if error is None:
          error = {"code": exc.code, "message": str(exc)}
          print(json.dumps(error, separators=(",", ":")), file=sys.stderr)
        else:
          print(json.dumps(error, separators=(",", ":")))
        return 2
      print(json.dumps(value, separators=(",", ":")))
      return 0

    if args.command == "preflight":
      candidate = validate_candidate(
        root,
        load_config(root),
        expected_sha=args.expected_sha,
      )
      print(json.dumps({"version": candidate.version, "commit": candidate.commit}))
      return 0

    if args.command == "stable-preflight":
      candidate = validate_stable_candidate(root, expected_sha=args.expected_sha)
      print(json.dumps({"version": candidate.version, "commit": candidate.commit}))
      return 0

    if args.command == "classify":
      paths = changed_paths(root, args.base, args.head)
      name, validation = classify_paths(paths, load_change_classes(root))
      print(json.dumps({
        "class": name or "default",
        "validation": validation,
        "paths": paths,
      }, separators=(",", ":")))
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
        push=args.push,
      )
      return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[outcome]

    if args.command == "verify-stable":
      outcome = verify_stable_local(
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

    if args.command == "stable-run":
      return run_stable_environment(
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

    if args.command == "stable-finalize":
      outcome = finalize_stable_results(
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
      candidate = (
        validate_stable_candidate(root)
        if args.stable
        else validate_candidate(root, config)
      )
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

    if args.command == "github-mode":
      config = load_config(root)
      print(github_mode(
        root,
        args.event_name,
        Path(args.event_path),
        args.branch,
        config["repository"]["integrationBranch"],
      ))
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
    ClassificationError,
    ConfigError,
    CurrentWorkError,
    HighRiskError,
    LifecycleError,
    TestCatalogueError,
    DependencySyncConflict,
    IssueMetadataError,
    LaneListError,
    LaneSelectionError,
    LaneRenderError,
    RepositoryPolicyError,
    RelationshipStoreError,
    RuntimeIdentityError,
    StateStoreError,
    TicketDependencyError,
    RepoInfoError,
    RepoCiError,
    ResultError,
    GitError,
    GuardError,
    VersionAdapterError,
    WorkspaceClaimError,
    WorkspaceCommandError,
    WorktreeError,
    ValueError,
  ) as exc:
    print(f"RepoWorkflow error: {exc}", file=sys.stderr)
    return 2
  raise AssertionError("unreachable")


if __name__ == "__main__":
  raise SystemExit(main())
