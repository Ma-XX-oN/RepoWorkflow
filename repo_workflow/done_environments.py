"""Execute configured consumer environments and reuse their actual observations."""
import json
from pathlib import Path
import tempfile

from .config import load_config
from .done_results import log_path, records
from .guard import Candidate
from .git import current_branch
from .results import _run_environment_for_candidate


def pending_environments(root: Path, plan: dict, os_name: str | None = None) -> list[dict]:
  """Select required consumer environments without applicable passing results.

  Parameters
  ----------
  root : Path
      Candidate checkout.
  plan : dict
      Exact source, parent and relevant inputs.
  os_name : str, optional
      Limit execution to environments available on this native platform.

  Returns
  -------
  list of dict
      Original configured environments still requiring execution.
  """
  if plan["engine"]:
    return []
  environments = [env for env in load_config(root)["environments"] if env["required"]]
  passed = {row["environmentResult"]["environment"] for row in records(root, plan)
    if row["testSHA"] == plan["candidate_sha"] and row["result"] == "succeeded"
    and row.get("doneParentSHA") == plan["parent_sha"]
    and row.get("doneInputsSHA256") == plan["inputs_sha256"]
    and row.get("environmentResult", {}).get("status") == "PASS"}
  return [env for env in environments if env["id"] not in passed
    and (os_name is None or env["platform"] in {"any", os_name})]


def run_environments(root: Path, plan: dict, os_name: str) -> int:
  """Run remaining consumer validation commands through their existing adapter.

  Parameters
  ----------
  root : Path
      Clean exact-source checkout.
  plan : dict
      Prepared completion identity.
  os_name : str
      Actual executing platform.

  Returns
  -------
  int
      Zero for applicable completion, one for failure, two for incomplete.
  """
  if plan["engine"]:
    return 0
  config = load_config(root)
  for environment in pending_environments(root, plan, os_name):
    with tempfile.TemporaryDirectory(prefix="rwf-done-environment-") as temporary:
      output = Path(temporary) / "result.json"
      status = _run_environment_for_candidate(root, config, environment["id"], output,
        Candidate(plan["version"], plan["candidate_sha"], plan["remote"]))
      observation = json.loads(output.read_text(encoding="utf-8"))
    row = {"kind": "integration", "runner": "configured-environment",
      "branch": current_branch(root), "uncommittedChanges": [],
      "headChangedDuringTest": False,
      "testSHA": plan["candidate_sha"], "testVersion": plan["version"],
      "result": {0: "succeeded", 1: "failed", 2: "incomplete"}[status],
      "doneParentSHA": plan["parent_sha"], "doneInputsSHA256": plan["inputs_sha256"],
      "environmentResult": observation}
    path = log_path(root, plan["issue"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
      handle.write(json.dumps(row, sort_keys=True) + "\n")
    from .done_results import publish_report
    publish_report(root, plan)
    if status:
      return status
  return 0
