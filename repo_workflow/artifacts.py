from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

from .git import changed_files, git, head_sha, repository_state
from .process import run_command


ARTIFACT_ENVIRONMENT_ID = "__repoworkflow_artifacts__"


class ArtifactError(RuntimeError):
  pass


@dataclass(frozen=True)
class ArtifactResult:
  status: str
  changed_files: list[str]
  failures: list[str]


def write_artifact_result(
  path: Path,
  result: ArtifactResult,
  *,
  version: str,
  commit: str,
) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps({
    "schema": 1,
    "environment": ARTIFACT_ENVIRONMENT_ID,
    "required": True,
    "version": version,
    "commit": commit,
    "status": result.status,
    "changedFiles": result.changed_files,
    "failures": result.failures,
  }, indent=2) + "\n", encoding="utf-8")


def _platform_name() -> str:
  if sys.platform.startswith("win"):
    return "windows"
  if sys.platform == "darwin":
    return "macos"
  if sys.platform.startswith("linux"):
    return "linux"
  return sys.platform


def _fingerprint(root: Path, relative: str) -> tuple[str, str | None]:
  path = root / relative
  if not path.exists():
    return ("missing", None)
  if path.is_dir():
    return ("directory", None)
  return ("file", hashlib.sha256(path.read_bytes()).hexdigest())


def materialize_artifacts(root: Path, config: dict) -> ArtifactResult:
  artifacts = config.get("artifacts", [])
  if not artifacts:
    return ArtifactResult("PASS", [], [])
  initial = changed_files(root)
  if initial:
    raise ArtifactError(
      "artifact materialization requires a clean worktree; found: "
      + ", ".join(initial)
    )
  failures: list[str] = []
  saw_incomplete = False
  actual_platform = _platform_name()
  for artifact in artifacts:
    required_platform = artifact.get("platform", "any")
    if required_platform not in {"any", actual_platform}:
      saw_incomplete = True
      failures.append(
        f"{artifact['id']} requires platform {required_platform}; "
        f"current platform is {actual_platform}"
      )
      break
    allowed = {path.replace("\\", "/") for path in artifact["outputs"]}
    before_changed = set(changed_files(root))
    before_state = repository_state(root)
    before_fingerprints = {
      path: _fingerprint(root, path) for path in before_changed
    }
    generated = run_command(artifact["generatorCommand"], root)
    after_state = repository_state(root)
    if after_state.commit != before_state.commit:
      raise ArtifactError(
        f"artifact {artifact['id']} generator modified Git history"
      )
    if after_state.head_ref != before_state.head_ref:
      raise ArtifactError(
        f"artifact {artifact['id']} generator modified HEAD reference"
      )
    if after_state.refs != before_state.refs:
      raise ArtifactError(
        f"artifact {artifact['id']} generator modified local Git refs"
      )
    after_changed = set(changed_files(root))
    touched = after_changed - before_changed
    for path in before_changed:
      if _fingerprint(root, path) != before_fingerprints[path]:
        touched.add(path)
    unexpected = sorted(touched - allowed)
    if unexpected:
      raise ArtifactError(
        f"artifact {artifact['id']} modified undeclared path(s): "
        + ", ".join(unexpected)
      )
    if generated.returncode == 2:
      saw_incomplete = True
      failures.append(f"{artifact['id']} generator incomplete")
      break
    if generated.returncode:
      failures.append(f"{artifact['id']} generator failed")
      break
    before_verify = {
      path: _fingerprint(root, path) for path in after_changed
    }
    before_verify_state = repository_state(root)
    verified = run_command(artifact["verifierCommand"], root)
    after_verify_state = repository_state(root)
    if after_verify_state.commit != before_verify_state.commit:
      raise ArtifactError(
        f"artifact {artifact['id']} verifier modified Git history"
      )
    if after_verify_state.head_ref != before_verify_state.head_ref:
      raise ArtifactError(
        f"artifact {artifact['id']} verifier modified HEAD reference"
      )
    if after_verify_state.refs != before_verify_state.refs:
      raise ArtifactError(
        f"artifact {artifact['id']} verifier modified local Git refs"
      )
    verifier_changes = set(changed_files(root))
    verifier_touched = verifier_changes - after_changed
    for path in after_changed:
      if _fingerprint(root, path) != before_verify[path]:
        verifier_touched.add(path)
    if verifier_touched:
      raise ArtifactError(
        f"artifact {artifact['id']} verifier modified repository state: "
        + ", ".join(sorted(verifier_touched))
      )
    if verified.returncode == 2:
      saw_incomplete = True
      failures.append(f"{artifact['id']} verifier incomplete")
      break
    if verified.returncode:
      failures.append(f"{artifact['id']} verifier failed")
      break
  changed = changed_files(root)
  all_allowed = {
    path.replace("\\", "/")
    for artifact in artifacts
    for path in artifact["outputs"]
  }
  unexpected = sorted(set(changed) - all_allowed)
  if unexpected:
    raise ArtifactError(
      "artifact materialization left undeclared changes: " + ", ".join(unexpected)
    )
  if saw_incomplete:
    status = "INCOMPLETE"
  elif failures:
    status = "FAIL"
  else:
    status = "PASS"
  return ArtifactResult(status, changed, failures)


def commit_artifact_changes(
  root: Path,
  result: ArtifactResult,
  message: str,
) -> str:
  if result.status != "PASS":
    raise ArtifactError("only a successful artifact result may be committed")
  if not result.changed_files:
    return head_sha(root)
  git(root, "add", "--all", "--", *result.changed_files)
  staged = sorted(
    line.strip().replace("\\", "/")
    for line in git(root, "diff", "--cached", "--name-only").stdout.splitlines()
    if line.strip()
  )
  expected = sorted(result.changed_files)
  if staged != expected:
    raise ArtifactError(
      "staged artifact paths do not match verified changes: "
      f"expected={expected}, staged={staged}"
    )
  git(root, "commit", "-m", message)
  return head_sha(root)
