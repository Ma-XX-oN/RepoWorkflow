"""Provider result-bundle boundary for consumer GitHub Actions jobs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
  sys.path.insert(0, str(ENGINE_ROOT))

from repo_workflow.repo_ci_dispatcher import RepoCiError, dispatch

_STAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")


def _environment() -> tuple[Path, Path, str, str, str]:
  required = (
    "RWF_REPO_CI_WORKSPACE", "RWF_REPO_CI_TRANSPORT_ROOT",
    "RWF_CANDIDATE", "RWF_BASE", "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
  )
  if any(not os.environ.get(name) for name in required):
    raise ValueError("consumer provider transport identity is incomplete")
  workspace = Path.cwd().resolve()
  if workspace != Path(os.environ["RWF_REPO_CI_WORKSPACE"]).resolve():
    raise ValueError("consumer workspace identity mismatch")
  return (
    workspace,
    Path(os.environ["RWF_REPO_CI_TRANSPORT_ROOT"]).resolve(),
    os.environ["RWF_CANDIDATE"],
    os.environ["RWF_BASE"],
    os.environ["GITHUB_REPOSITORY"],
  )


def _transfer(action: str, stage: str) -> bool:
  if _STAGE.fullmatch(stage) is None:
    raise ValueError("invalid provider stage identity")
  workspace, transport_root, commit, base, repository = _environment()
  filename = stage + ".json"
  if action == "publish":
    source = transport_root / "repoworkflow-result"
    destination = transport_root / "repoworkflow-provider-bundles" / stage
  else:
    source = transport_root / "downloaded-provider" / (
      "repoworkflow-provider-result-" + stage
    )
    destination = transport_root / "repoworkflow-results" / ("stage-" + stage)
  request = {
    "contract_version": 1,
    "operation": action,
    "invocation_id": (
      os.environ["GITHUB_RUN_ID"] + "-" +
      os.environ["GITHUB_RUN_ATTEMPT"] + "-" + stage
    ),
    "candidate": {"repository": repository, "commit": commit, "base": base},
    "requirements": {
      "stages": [], "capabilities": [], "artifacts": [filename],
    },
    "inputs": {
      "source_dir": str(source), "destination_dir": str(destination),
    },
  }
  response = dispatch(
    workspace, action, json.dumps(request).encode("utf-8"),
  )
  if response["status"] != "ok":
    print(json.dumps(response["diagnostics"]), file=sys.stderr)
    return False
  if response["candidate"] != request["candidate"]:
    raise ValueError("provider transport identity mismatch")
  print(json.dumps(response["observations"], separators=(",", ":")))
  return True


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("action", choices=("publish", "fetch", "fetch-all"))
  parser.add_argument("--stage")
  args = parser.parse_args(argv)
  try:
    if args.action != "fetch-all":
      if not args.stage:
        parser.error("--stage is required")
      return 0 if _transfer(args.action, args.stage) else 2
    matrix = json.loads(os.environ["RWF_MATRIX"])
    if not isinstance(matrix, dict) or set(matrix) != {"include"}:
      raise ValueError("provider matrix is malformed")
    stages = matrix["include"]
    if not isinstance(stages, list) or not stages:
      raise ValueError("provider matrix contains no stages")
    values = [item.get("id") for item in stages if isinstance(item, dict)]
    if len(values) != len(stages) or len(values) != len(set(values)):
      raise ValueError("provider matrix has invalid stage membership")
    succeeded = True
    for stage in values:
      succeeded = _transfer("fetch", stage) and succeeded
    return 0 if succeeded else 2
  except (RepoCiError, ValueError, KeyError, TypeError) as exc:
    print(f"repo-ci result transport: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
