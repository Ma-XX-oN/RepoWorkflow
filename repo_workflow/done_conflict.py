"""Retain actual integration conflicts and a reviewable outgoing notification."""
import json
from pathlib import Path

from .git import git
from .state_store import durable_store


def record_conflict(root: Path, plan: dict, diagnostic: str) -> dict:
  """Publish conflict provenance and retain an unsent notification draft.

  The approved outgoing client attempts delivery before receipt publication.
  The receipt retains the actual sent/failed outcome and is reused on resume.

  Parameters
  ----------
  root : Path
      Repository with normal access to its authoritative Git remote.
  plan : dict
      Selected source, issue and current parent.
  diagnostic : str
      Actual reconstruction error.

  Returns
  -------
  dict
      Durable conflict receipt, including the actual notification disposition.
  """
  from .done_workflow import remote_refs
  key = f"issues/{plan['issue']}/done-conflicts/{plan['candidate_sha']}-{plan['parent_sha']}"
  handoff = durable_store(root).read(key)["value"]
  recipient = git(root, "log", "-1", "--format=%ae", plan["source_sha"]).stdout.strip()
  result = {"status": "conflict", "issue": plan["issue"], "prelim_ref": plan["prelim_ref"],
    "source_sha": plan["candidate_sha"], "parent_sha": plan["parent_sha"],
    "diagnostic": diagnostic, "handoff": handoff,
    "notification": {"status": "pending", "to": recipient,
      "subject": f"RWF issue {plan['issue']}: integration conflict",
      "body": f"Issue {plan['issue']} could not integrate into {plan['destination']}.\n"
        f"Source: {plan['candidate_sha']}\nParent: {plan['parent_sha']}\n"
        + handoff["merge_output"]}}
  suffix = plan["prelim_ref"].removeprefix("refs/heads/PRELIM-") + "-" + plan["parent_sha"]
  ref = "refs/tags/rwf-prelim-conflict-v1-" + suffix
  observed = remote_refs(root, plan["remote"], ref)
  if observed:
    git(root, "fetch", "--no-tags", plan["remote"], ref)
    result = json.loads(git(root, "show", "-s", "--format=%B", "FETCH_HEAD").stdout)
  if not observed:
    from .done_email import send_conflict_email
    result["notification"] = send_conflict_email(root, result["notification"])
    tree = git(root, "rev-parse", plan["candidate_sha"] + "^{tree}").stdout.strip()
    receipt = git(root, "commit-tree", tree, "-p", plan["candidate_sha"],
      "-m", json.dumps(result, sort_keys=True)).stdout.strip()
    git(root, "push", "--force-with-lease=" + ref + ":", plan["remote"], receipt + ":" + ref)
  result["receipt_ref"] = ref
  return result
