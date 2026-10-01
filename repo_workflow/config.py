from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(RuntimeError):
  pass


def _command(value: Any, label: str) -> list[str]:
  if not isinstance(value, list) or not value or not all(
    isinstance(item, str) and item for item in value
  ):
    raise ConfigError(f"{label} must be a non-empty array of strings")
  return list(value)


def _strings(value: Any, label: str) -> list[str]:
  if not isinstance(value, list) or not all(
    isinstance(item, str) and item for item in value
  ):
    raise ConfigError(f"{label} must be an array of non-empty strings")
  return list(value)


def _validate_environment(value: Any, seen: set[str]) -> dict[str, Any]:
  if not isinstance(value, dict):
    raise ConfigError("each environment must be an object")
  allowed = {
    "id", "required", "platform", "capabilities", "validationCommand"
  }
  unknown = sorted(set(value) - allowed)
  if unknown:
    raise ConfigError(
      "environment contains unsupported fields: " + ", ".join(unknown)
    )
  env_id = value.get("id")
  if not isinstance(env_id, str) or not env_id:
    raise ConfigError("environment id must be a non-empty string")
  if env_id in seen:
    raise ConfigError(f"duplicate environment id: {env_id}")
  seen.add(env_id)
  command = _command(value.get("validationCommand"), f"{env_id}.validationCommand")
  platform = value.get("platform", "any")
  if platform not in {"any", "linux", "windows", "macos"}:
    raise ConfigError(f"unsupported platform for {env_id}: {platform}")
  result = dict(value)
  result["required"] = bool(value.get("required", True))
  result["platform"] = platform
  result["capabilities"] = _strings(
    value.get("capabilities", []), f"{env_id}.capabilities"
  )
  result["validationCommand"] = command
  return result


def _validate_artifact(value: Any, seen: set[str]) -> dict[str, Any]:
  if not isinstance(value, dict):
    raise ConfigError("each artifact must be an object")
  allowed = {
    "id", "generatorCommand", "verifierCommand", "outputs", "committed",
    "platform", "capabilities",
  }
  unknown = sorted(set(value) - allowed)
  if unknown:
    raise ConfigError("artifact contains unsupported fields: " + ", ".join(unknown))
  artifact_id = value.get("id")
  if not isinstance(artifact_id, str) or not artifact_id:
    raise ConfigError("artifact id must be a non-empty string")
  if artifact_id in seen:
    raise ConfigError(f"duplicate artifact id: {artifact_id}")
  seen.add(artifact_id)
  outputs = _strings(value.get("outputs"), f"{artifact_id}.outputs")
  if not outputs:
    raise ConfigError(f"{artifact_id}.outputs must be non-empty")
  platform = value.get("platform", "any")
  if platform not in {"any", "linux", "windows", "macos"}:
    raise ConfigError(f"unsupported artifact platform for {artifact_id}: {platform}")
  result = dict(value)
  generator = _command(
    value.get("generatorCommand"), f"{artifact_id}.generatorCommand"
  )
  verifier = _command(
    value.get("verifierCommand"), f"{artifact_id}.verifierCommand"
  )
  if verifier == generator:
    raise ConfigError(
      f"{artifact_id} must declare an independent verifier command"
    )
  committed = value.get("committed", True)
  if committed is not True:
    raise ConfigError(
      f"{artifact_id} artifacts are only for committed generated artifacts"
    )
  result["generatorCommand"] = generator
  result["verifierCommand"] = verifier
  result["outputs"] = outputs
  result["committed"] = True
  result["platform"] = platform
  result["capabilities"] = _strings(
    value.get("capabilities", []), f"{artifact_id}.capabilities"
  )
  return result


def load_config(root: Path) -> dict[str, Any]:
  path = root / ".ci" / "repoworkflow.json"
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except FileNotFoundError as exc:
    raise ConfigError(f"missing RepoWorkflow configuration: {path}") from exc
  except json.JSONDecodeError as exc:
    raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
  if not isinstance(data, dict) or data.get("schema") != 1:
    raise ConfigError("repoworkflow.json must declare schema 1")
  allowed_top = {
    "schema", "versionCommand", "repository", "environments", "artifacts"
  }
  unknown = sorted(set(data) - allowed_top)
  if unknown:
    raise ConfigError("configuration contains unsupported fields: " + ", ".join(unknown))
  version_command = _command(data.get("versionCommand"), "versionCommand")
  repository = data.get("repository")
  if not isinstance(repository, dict):
    raise ConfigError("repository configuration is required")
  unknown_repository = sorted(
    set(repository) - {"integrationBranch", "authoritativeRemote"}
  )
  if unknown_repository:
    raise ConfigError(
      "repository contains unsupported fields: " + ", ".join(unknown_repository)
    )
  integration = repository.get("integrationBranch")
  remote = repository.get("authoritativeRemote")
  if not isinstance(integration, str) or not integration:
    raise ConfigError("repository.integrationBranch is required")
  if not isinstance(remote, str) or not remote:
    raise ConfigError("repository.authoritativeRemote is required")
  environments = data.get("environments")
  if not isinstance(environments, list) or not environments:
    raise ConfigError("at least one environment is required")
  env_seen: set[str] = set()
  validated_envs = [_validate_environment(item, env_seen) for item in environments]
  artifacts = data.get("artifacts", [])
  if not isinstance(artifacts, list):
    raise ConfigError("artifacts must be an array")
  artifact_seen: set[str] = set()
  validated_artifacts = [_validate_artifact(item, artifact_seen) for item in artifacts]
  output_owners: dict[str, str] = {}
  for artifact in validated_artifacts:
    for output in artifact["outputs"]:
      normalized = output.replace("\\", "/")
      prior = output_owners.get(normalized)
      if prior is not None:
        raise ConfigError(
          f"generated output {normalized} is declared by both {prior} and "
          f"{artifact['id']}"
        )
      output_owners[normalized] = artifact["id"]
  result = dict(data)
  result["versionCommand"] = version_command
  result["repository"] = dict(repository)
  result["environments"] = validated_envs
  result["artifacts"] = validated_artifacts
  return result
