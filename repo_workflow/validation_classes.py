from __future__ import annotations

import json
from pathlib import Path
import tempfile

from .config import load_config
from .git import head_sha
from .guard import Candidate
from .results import _run_environment_for_candidate
from .version_adapter import read_development_version


class ValidationClassError(ValueError):
  pass


def _environment_pool(config: dict, kind: str) -> list[dict]:
  if kind == "ART":
    return list(config["environments"])
  if kind == "AIT":
    return list(config.get("integrationEnvironments", []))
  raise ValidationClassError(f"unknown validation class: {kind}")


def selected_environments(
  config: dict,
  kind: str,
  *,
  fast: bool = False,
  group: str | None = None,
) -> list[dict]:
  if fast and group is not None:
    raise ValidationClassError("--fast and --group are mutually exclusive")
  values = _environment_pool(config, kind)
  if fast:
    if kind != "ART":
      raise ValidationClassError("--fast is valid only for regression validation")
    values = [value for value in values if value.get("fast", False)]
    if not values:
      raise ValidationClassError("no fast regression validation is declared")
  if group is not None:
    values = [value for value in values if group in value.get("groups", [])]
    if not values:
      raise ValidationClassError(
        f"validation group is not declared for {kind}: {group}"
      )
  return values


def run_validation_class(
  root: Path,
  kind: str,
  *,
  fast: bool = False,
  group: str | None = None,
) -> str:
  root = root.resolve()
  config = load_config(root)
  environments = selected_environments(
    config,
    kind,
    fast=fast,
    group=group,
  )
  if not environments:
    return "PASS"

  candidate = Candidate(
    version=read_development_version(root, config),
    commit=head_sha(root),
    remote=config["repository"]["authoritativeRemote"],
  )
  statuses: list[str] = []
  with tempfile.TemporaryDirectory(prefix="repoworkflow-class-") as directory:
    result_dir = Path(directory)
    for environment in environments:
      path = result_dir / f"{environment['id']}.json"
      _run_environment_for_candidate(
        root,
        {
          **config,
          "environments": [
            *config["environments"],
            *config.get("integrationEnvironments", []),
          ],
        },
        environment["id"],
        path,
        candidate,
      )
      value = json.loads(path.read_text(encoding="utf-8"))
      if environment.get("required", True):
        statuses.append(str(value.get("status")))

  if "FAIL" in statuses:
    return "FAIL"
  if "INCOMPLETE" in statuses:
    return "INCOMPLETE"
  if any(status != "PASS" for status in statuses):
    return "INCOMPLETE"
  return "PASS"
