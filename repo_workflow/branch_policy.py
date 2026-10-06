from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from .git import git
from .parent_branch import ParentBranchError, recover_parent_branch


class BranchPolicyError(RuntimeError):
  pass


def _validate_rule(value: object, label: str, *, pattern: bool = False) -> dict:
  if not isinstance(value, dict):
    raise BranchPolicyError(f"{label} must be an object")
  allowed = {"allowedDependencies"}
  if pattern:
    allowed.add("pattern")
  unknown = sorted(set(value) - allowed)
  if unknown:
    raise BranchPolicyError(
      f"{label} has unsupported fields: {', '.join(unknown)}"
    )
  if pattern:
    match = value.get("pattern")
    if not isinstance(match, str) or not match:
      raise BranchPolicyError(f"{label}.pattern is required")
  dependencies = value.get("allowedDependencies", [])
  if not isinstance(dependencies, list) or not all(
    isinstance(item, str) and item for item in dependencies
  ):
    raise BranchPolicyError(
      f"{label}.allowedDependencies must be an array"
    )
  result = dict(value)
  result["allowedDependencies"] = list(dependencies)
  return result


def _load_policy(root: Path) -> dict:
  path = root / ".ci" / "branch-policy.json"
  try:
    value = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as exc:
    raise BranchPolicyError(f"missing branch policy: {path}") from exc
  except json.JSONDecodeError as exc:
    raise BranchPolicyError(f"invalid branch policy JSON: {exc}") from exc
  if not isinstance(value, dict) or value.get("schema") != 2:
    raise BranchPolicyError("branch policy must declare schema 2")
  allowed_top = {"schema", "integrationBranch", "branches", "patterns"}
  unknown = sorted(set(value) - allowed_top)
  if unknown:
    raise BranchPolicyError(
      "branch policy has unsupported fields: " + ", ".join(unknown)
    )
  integration = value.get("integrationBranch")
  if not isinstance(integration, str) or not integration:
    raise BranchPolicyError("branch policy integrationBranch is required")
  branches = value.get("branches", {})
  patterns = value.get("patterns", [])
  if not isinstance(branches, dict):
    raise BranchPolicyError("branch policy branches must be an object")
  if not isinstance(patterns, list):
    raise BranchPolicyError("branch policy patterns must be an array")
  result = dict(value)
  result["branches"] = {
    name: _validate_rule(rule, f"branches.{name}")
    for name, rule in branches.items()
  }
  result["patterns"] = [
    _validate_rule(rule, f"patterns[{index}]", pattern=True)
    for index, rule in enumerate(patterns)
  ]
  return result


def _rule_for(policy: dict, branch: str) -> dict | None:
  exact = policy["branches"].get(branch)
  if exact is not None:
    return dict(exact)
  for rule in policy["patterns"]:
    if fnmatch.fnmatchcase(branch, rule["pattern"]):
      return {
        key: value
        for key, value in rule.items()
        if key != "pattern"
      }
  return None


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
  result = git(
    root,
    "merge-base",
    "--is-ancestor",
    ancestor,
    descendant,
    check=False,
  )
  return result.returncode == 0


def _parent_ref(root: Path, remote: str, parent: str) -> str:
  remote_ref = f"refs/remotes/{remote}/{parent}"
  if git(root, "show-ref", "--verify", remote_ref, check=False).returncode == 0:
    return remote_ref
  local_ref = f"refs/heads/{parent}"
  if git(root, "show-ref", "--verify", local_ref, check=False).returncode == 0:
    return local_ref
  raise BranchPolicyError(f"parent branch is unavailable: {parent}")


def check_branch_policy(
  root: Path,
  branch: str,
  pr_base: str | None,
  remote: str,
) -> None:
  policy = _load_policy(root)
  integration = policy["integrationBranch"]
  if branch == integration:
    return
  rule = _rule_for(policy, branch)
  if rule is None:
    raise BranchPolicyError(f"no branch policy rule matches {branch}")

  fetched = git(
    root,
    "fetch",
    "--no-tags",
    remote,
    f"+refs/heads/*:refs/remotes/{remote}/*",
    check=False,
  )
  if fetched.returncode:
    detail = (fetched.stderr or fetched.stdout).strip()
    raise BranchPolicyError(f"cannot refresh branch ancestry: {detail}")

  try:
    parent = recover_parent_branch(root, branch)
  except ParentBranchError as error:
    raise BranchPolicyError(str(error)) from error
  if pr_base is not None and pr_base != parent:
    raise BranchPolicyError(
      f"pull request base {pr_base} does not match branch parent {parent}"
    )

  parent_ref = _parent_ref(root, remote, parent)
  head = git(root, "rev-parse", "HEAD").stdout.strip()
  merge_base_result = git(root, "merge-base", head, parent_ref, check=False)
  if merge_base_result.returncode:
    raise BranchPolicyError(
      f"branch {branch} has no merge base with {parent}"
    )
  merge_base = merge_base_result.stdout.strip()
  merge_lines = git(
    root,
    "rev-list",
    "--reverse",
    "--merges",
    "--parents",
    f"{merge_base}..{head}",
  ).stdout.splitlines()
  allowed_dependencies = list(rule["allowedDependencies"])
  violations: list[str] = []
  for line in merge_lines:
    parts = line.split()
    if len(parts) < 3:
      continue
    merge_sha = parts[0]
    for imported in parts[2:]:
      if _is_ancestor(root, imported, parent_ref):
        continue
      matched = False
      for dependency in allowed_dependencies:
        dependency_ref = f"refs/remotes/{remote}/{dependency}"
        exists = git(
          root,
          "show-ref",
          "--verify",
          dependency_ref,
          check=False,
        )
        if (
          exists.returncode == 0
          and _is_ancestor(root, imported, dependency_ref)
        ):
          matched = True
          break
      if not matched:
        violations.append(
          f"merge {merge_sha} imports undeclared history at {imported}"
        )
  if violations:
    raise BranchPolicyError(
      "branch policy failed:\n- " + "\n- ".join(violations)
    )
