"""Execute the functional PRELIM workflow through Git and registered tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import load_config
from .done_results import import_reports, log_path, pending_groups, platform_name, publish_report
from .done_submission import DoneSubmissionError, prepare_submission_candidate
from .git import changed_files, git
from .owned_commit import commit_owned_files
from .prelim_queue import discover_ready_prelims, latest_prelims, parse_ready_prelim, prelim_ref_for_version
from .prelim_submission import PREFIX, decode_submission, publish_submission, submission_ref
from .source_tip import source_tip
from .test_results_reader import TestCommandError


def remote_refs(root: Path, remote: str, pattern: str) -> dict[str, str]:
  """Read exact advertised Git refs.

  Parameters
  ----------
  root : Path
      Repository checkout.
  remote, pattern : str
      Configured remote and ref pattern.

  Returns
  -------
  dict
      Ref-to-object mapping.
  """
  return {line.split("\t")[1]: line.split("\t")[0] for line in
          git(root, "ls-remote", "--refs", remote, pattern).stdout.splitlines()}


def checkout_candidate(root: Path, candidate: str, *, purpose: str = "tests") -> Path:
  """Obtain a clean checkout without restricting where tests may run.

  Parameters
  ----------
  root : Path
      Clone holding the candidate object.
  candidate : str
      Exact effective source SHA.
  purpose : str
      Internal construction purpose; test execution may reuse the caller checkout.

  Returns
  -------
  Path
      Existing matching checkout or a detached construction checkout.
  """
  if purpose == "tests" and source_tip(root) == candidate:
    return root
  common = Path(git(root, "rev-parse", "--git-common-dir").stdout.strip())
  if not common.is_absolute():
    common = root / common
  workspace = common.resolve() / ("rwf-prelim-" + purpose) / candidate
  if not workspace.exists():
    workspace.parent.mkdir(parents=True, exist_ok=True)
    git(root, "worktree", "add", "--detach", str(workspace), candidate)
  if purpose.startswith("accept-") and source_tip(workspace) != candidate:
    issue = int(purpose.split("-")[1])
    allowed = {f".repoworkflow/validation/testResults-{issue}.jsonl", ".repoworkflow/tickets.csv"}
    modified = git(workspace, "diff", "--name-only", candidate, "HEAD").stdout.splitlines()
    if changed_files(workspace) or not set(modified).issubset(allowed):
      raise TestCommandError("prepared acceptance checkout has changed source")
    git(workspace, "reset", "--hard", candidate)
  if source_tip(workspace) != candidate or changed_files(workspace):
    raise TestCommandError("candidate checkout changed; reconcile before resuming done")
  return workspace


def completed_submission(root: Path, issue: int, remote: str = "origin") -> dict | None:
  """Read durable completion after checking the actual parent history.

  Parameters
  ----------
  root : Path
      Clone used for provider readback.
  issue : int
      Issue number.
  remote : str
      Authoritative Git remote.

  Returns
  -------
  dict or None
      Latest actual accepted result, including after PRELIM retirement.
  """
  prefix = "refs/tags/rwf-done-v1-"
  refs = remote_refs(root, remote, prefix + f"issue-{issue}.*")
  if not refs:
    return None
  ref = max(refs, key=lambda name: parse_ready_prelim(
    "refs/heads/PRELIM-" + name.removeprefix(prefix), "0" * 40).version_order)
  git(root, "fetch", "--no-tags", remote, ref)
  if git(root, "cat-file", "-t", refs[ref]).stdout.strip() != "tag":
    raise TestCommandError("completion receipt must be an annotated tag")
  value = json.loads(git(root, "cat-file", "-p", refs[ref]).stdout.split("\n\n", 1)[1])
  if (value.get("status") != "done" or value.get("issue") != issue
      or "rwf-done-v1-" + value.get("version_suffix", "") != ref.removeprefix("refs/tags/")):
    raise TestCommandError("completion receipt identity differs")
  git(root, "fetch", "--no-tags", remote, "refs/heads/" + value["destination"])
  if git(root, "merge-base", "--is-ancestor", value["landed_sha"], "FETCH_HEAD", check=False).returncode:
    raise TestCommandError("completed submission is absent from parent history")
  return value


def prepare_done(root: Path, prelim_ref: str, *, engine_root: Path, remote: str = "origin") -> dict:
  """Select the latest submission and reconstruct stale source before testing.

  Parameters
  ----------
  root, engine_root : Path
      Repository checkout and installed workflow engine.
  prelim_ref : str
      Requested versioned PRELIM ref.
  remote : str
      Authoritative remote.

  Returns
  -------
  dict
      Portable exact-source execution plan, ignored result or completed result.
  """
  requested = parse_ready_prelim(prelim_ref, "0" * 40)
  if requested is None:
    raise TestCommandError("done requires a versioned PRELIM ref")
  issue = int(requested.umbrella.removeprefix("issue-"))
  terminal = completed_submission(root, issue, remote)
  inventory = discover_ready_prelims(remote_refs(root, remote, f"refs/heads/PRELIM-issue-{issue}.*"))
  selected = latest_prelims(inventory)
  if terminal is not None and (not selected or tuple(terminal["version_order"]) >= selected[0].version_order):
    return terminal
  if not selected or selected[0].ref != prelim_ref:
    return {"status": "ignored", "issue": issue, "reason": "superseded PRELIM"}
  ready = selected[0]
  git(root, "fetch", "--no-tags", remote, ready.ref)
  git(root, "fetch", "--no-tags", remote, submission_ref(ready.guid))
  message = git(root, "show", "-s", "--format=%B", "FETCH_HEAD").stdout.rstrip("\n")
  repository = json.loads(message.removeprefix(PREFIX))["repository"]
  saved = decode_submission(message, repository=repository, guid=ready.guid)
  if saved["prelim_ref"] != ready.ref or saved["candidate_sha"] != ready.sha:
    raise TestCommandError("PRELIM differs from its recorded submission")
  parent_ref = "refs/heads/" + saved["destination"]
  parent = remote_refs(root, remote, parent_ref).get(parent_ref)
  if parent is None:
    raise TestCommandError("authoritative parent is unavailable")
  git(root, "fetch", "--no-tags", remote, parent_ref)
  config = load_config(root) if (root / ".ci/repoworkflow.json").is_file() else None
  if parent != saved["parent_sha"]:
    if (root / ".repoworkflow/tickets.csv").is_file():
      from .ticket_merge import configure_ticket_merge_driver
      configure_ticket_merge_driver(root, engine_root)
    try:
      candidate, version = prepare_submission_candidate(
        root, ready.sha, parent, config, issue, engine_root)
    except DoneSubmissionError as error:
      if "durable handoff:" not in str(error):
        raise
      from .done_conflict import record_conflict
      return record_conflict(root, {**saved, "issue": issue, "remote": remote,
        "parent_sha": parent}, str(error))
    updated = {**saved, "parent_sha": parent, "candidate_sha": candidate,
               "version": version, "prelim_ref": prelim_ref_for_version(version)}
    ready = parse_ready_prelim(updated["prelim_ref"], candidate, destination=saved["destination"])
    updated["guid"] = ready.guid
    updated["inputs_sha256"] = hashlib.sha256(json.dumps({
      "tree": git(root, "rev-parse", candidate + "^{tree}").stdout.strip(),
      "parent": parent, "release": saved["release"]}, sort_keys=True).encode()).hexdigest()
    publish_submission(root, updated, remote=remote)
    saved = updated
  return {**saved, "status": "prepared", "issue": issue, "remote": remote,
          "version_suffix": ready.version, "version_order": list(ready.version_order),
          "engine": config is None,
          "platforms": ["linux", "windows", "macos"] if config is None else sorted({
            item["platform"] for item in config["environments"] if item["required"]})}


def run_done_tests(root: Path, plan: dict) -> dict:
  """Run remaining registered tests on this actual platform and retain results.

  Parameters
  ----------
  root : Path
      Checkout containing the planned source object.
  plan : dict
      Prepared execution plan.

  Returns
  -------
  dict
      Actual worker disposition and report ref; missing MITs are never PASS.
  """
  from .test_cli import _run_group_set
  workspace = checkout_candidate(root, plan["candidate_sha"])
  import_reports(workspace, plan)
  os_name = platform_name()
  if "any" not in plan["platforms"] and os_name not in plan["platforms"]:
    return {"status": "not-required", "platform": os_name}
  path = log_path(workspace, plan["issue"])
  for stage in ("regression", "integration"):
    groups = pending_groups(workspace, plan, stage, os_name)
    if not groups:
      continue
    previous = path.read_bytes() if path.exists() else b""
    status = _run_group_set(workspace, stage, groups, reuse=False)
    added = path.read_bytes()[len(previous):].decode("utf-8").splitlines()
    rows = [json.loads(line) for line in added]
    for row in rows:
      row.update(testVersion=plan["version"], doneParentSHA=plan["parent_sha"],
                 doneInputsSHA256=plan["inputs_sha256"])
    path.write_bytes(previous + ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode())
    report = publish_report(workspace, plan)
    if status:
      if status == 1:
        from .terminal_tag import publish_terminal_tag
        publish_terminal_tag(workspace, stage=stage, remote=plan["remote"],
          version=plan["version"], candidate=plan["candidate_sha"],
          outcome="FAIL", canonical_log=path, push=True)
      return {"status": "failed" if status == 1 else "incomplete", "report_ref": report}
    from .terminal_tag import publish_terminal_tag
    publish_terminal_tag(workspace, stage=stage, remote=plan["remote"],
      version=plan["version"], candidate=plan["candidate_sha"],
      outcome="PASS", canonical_log=path, push=True)
  from .done_environments import run_environments
  status = run_environments(workspace, plan, os_name)
  if status == 1:
    from .terminal_tag import publish_terminal_tag
    publish_terminal_tag(workspace, stage="integration", remote=plan["remote"],
      version=plan["version"], candidate=plan["candidate_sha"],
      outcome="FAIL", canonical_log=path, push=True)
  return {"status": {0: "tested", 1: "failed", 2: "incomplete"}[status],
          "platform": os_name, "report_ref": publish_report(workspace, plan)}


def accept_done(root: Path, plan: dict) -> dict:
  """Accept complete results with an atomic expected-parent Git update.

  Parameters
  ----------
  root : Path
      Clone used to collect results and update the parent.
  plan : dict
      Exact tested submission and expected parent.

  Returns
  -------
  dict
      Done, waiting, stale or superseded disposition after Git readback.
  """
  from .manual_test_catalogue import read_manual_cases
  from .manual_test_result import read_manual_case_results
  from .ticket_admission import parse_policy, policy_path
  prior = completed_submission(root, plan["issue"], plan["remote"])
  if prior is not None and tuple(prior["version_order"]) >= tuple(plan["version_order"]):
    return prior
  parent_ref = "refs/heads/" + plan["destination"]
  if remote_refs(root, plan["remote"], parent_ref).get(parent_ref) != plan["parent_sha"]:
    return {"status": "stale", "prelim_ref": plan["prelim_ref"]}
  workspace = checkout_candidate(root, plan["candidate_sha"],
    purpose=f"accept-{plan['issue']}-{plan['parent_sha']}")
  import_reports(workspace, plan)
  missing = {os_name: pending_groups(workspace, plan, "integration", os_name)
             for os_name in plan["platforms"]}
  missing = {os_name: list(groups) for os_name, groups in missing.items() if groups}
  from .done_environments import pending_environments
  environments = [env["id"] for env in pending_environments(workspace, plan)]
  cases = read_manual_cases(workspace, plan["issue"])
  manual = read_manual_case_results(workspace, plan["issue"], plan["candidate_sha"], cases=cases) if cases else {}
  if "failed" in manual.values():
    raise TestCommandError("manual integration failed; repair before done")
  pending_manual = [case.name for case in cases if manual.get(case.name) != "succeeded"]
  if missing or pending_manual or environments:
    return {"status": "waiting", "missing": missing, "manual": pending_manual,
            "environments": environments,
            "prelim_ref": plan["prelim_ref"]}
  parent_ref = "refs/heads/" + plan["destination"]
  if remote_refs(root, plan["remote"], parent_ref).get(parent_ref) != plan["parent_sha"]:
    return {"status": "stale", "prelim_ref": plan["prelim_ref"]}
  refs = latest_prelims(discover_ready_prelims(remote_refs(
    root, plan["remote"], f"refs/heads/PRELIM-issue-{plan['issue']}.*")))
  if not refs or refs[0].ref != plan["prelim_ref"] or refs[0].sha != plan["candidate_sha"]:
    return {"status": "ignored", "reason": "superseded PRELIM"}
  git(workspace, "fetch", "--no-tags", plan["remote"], parent_ref)
  policy = git(workspace, "show", plan["parent_sha"] + ":" + policy_path(plan["destination"]).as_posix(), check=False)
  if policy.returncode == 0 and plan["issue"] not in parse_policy(policy.stdout):
    raise TestCommandError("current parent admission policy denies this issue")
  _require_dependencies(workspace, plan)
  _record_reused_phases(workspace, plan)
  path = log_path(workspace, plan["issue"])
  commit_owned_files(workspace, [path.relative_to(workspace).as_posix()], "test: collect accepted PRELIM reports")
  tested_report = git(workspace, "rev-parse", "HEAD").stdout.strip()
  if source_tip(workspace, tested_report) != plan["candidate_sha"]:
    raise TestCommandError("test inputs changed before integration")
  landed = _complete_lifecycle(workspace, plan)
  result = {**plan, "status": "done", "landed_sha": landed,
            "tested_source_sha": plan["candidate_sha"], "tested_report_sha": tested_report}
  name = "rwf-done-v1-" + plan["version_suffix"]
  receipt_ref = "refs/tags/" + name
  local = git(workspace, "show-ref", "--verify", receipt_ref, check=False)
  if local.returncode == 0:
    git(workspace, "tag", "-d", name)
  git(workspace, "tag", "-a", name, landed, "-m", json.dumps(result, sort_keys=True))
  receipt_sha = git(workspace, "rev-parse", receipt_ref).stdout.strip()
  pushed = git(workspace, "push", "--atomic",
    "--force-with-lease=" + parent_ref + ":" + plan["parent_sha"],
    "--force-with-lease=" + plan["prelim_ref"] + ":" + plan["candidate_sha"],
    "--force-with-lease=" + receipt_ref + ":", plan["remote"],
    landed + ":" + parent_ref, ":" + plan["prelim_ref"], receipt_ref + ":" + receipt_ref,
    check=False)
  observed = remote_refs(workspace, plan["remote"], receipt_ref)
  if observed.get(receipt_ref) == receipt_sha:
    return completed_submission(workspace, plan["issue"], plan["remote"])
  if pushed.returncode and remote_refs(workspace, plan["remote"], parent_ref).get(parent_ref) != plan["parent_sha"]:
    return {"status": "stale", "prelim_ref": plan["prelim_ref"]}
  raise TestCommandError("done publication UNKNOWN; reconcile Git refs before retrying")


def _require_dependencies(root: Path, plan: dict) -> None:
  """Require completed declared dependencies from the assembled repository.

  Parameters
  ----------
  root : Path
      Current-parent candidate checkout.
  plan : dict
      Issue being integrated.
  """
  from .relationship_store import RelationshipStore
  if not (root / ".repoworkflow/tickets.csv").exists():
    return  # Repositories without a synchronized graph declare no CSV dependencies.
  graph = RelationshipStore(root).read()
  issue = graph.graph.issues.get(str(plan["issue"]))
  if issue is None:
    raise TestCommandError("issue is missing from synchronized ticket state")
  for dependency in issue.depends_on:
    if graph.states[str(dependency)].state != "completed":
      raise TestCommandError("incomplete dependency: issue-" + str(dependency))


def _record_reused_phases(root: Path, plan: dict) -> None:
  """Record aggregate reuse explicitly, retaining original execution reports.

  Parameters
  ----------
  root : Path
      Checkout whose real group/platform coverage was checked by accept_done.
  plan : dict
      Exact tested identity.
  """
  from .test_catalogue import stage_groups
  from .terminal_tag import publish_terminal_tag
  path = log_path(root, plan["issue"])
  for stage in ("regression", "integration"):
    summary = {"kind": stage, "testSHA": plan["candidate_sha"],
      "testVersion": plan["version"], "branch": plan["prelim_ref"].removeprefix("refs/heads/"),
      "result": "succeeded", "runner": "aggregate", "reused": True,
      "reusable": True, "headChangedDuringTest": False, "uncommittedChanges": [],
      "catalogueSHA256": hashlib.sha256((root / ".ci/tests.json").read_bytes()).hexdigest(),
      "doneParentSHA": plan["parent_sha"], "doneInputsSHA256": plan["inputs_sha256"],
      "platforms": plan["platforms"], "selectedGroups": list(stage_groups(root, stage)),
      "evidenceSHA256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
      handle.write(json.dumps(summary, sort_keys=True) + "\n")
    publish_terminal_tag(root, stage=stage, remote=plan["remote"], version=plan["version"],
      candidate=plan["candidate_sha"], outcome="PASS", canonical_log=path, push=True)


def _complete_lifecycle(root: Path, plan: dict) -> str:
  """Prepare legal workflow metadata, keeping the actual tested SHA explicit.

  Parameters
  ----------
  root : Path
      Isolated tested checkout.
  plan : dict
      Issue and exact tested source.

  Returns
  -------
  str
      Proposed landed commit containing reports and lifecycle state.
  """
  from .relationship_store import RelationshipStore
  store = RelationshipStore(root)
  tickets = store.read()
  state = tickets.states[str(plan["issue"])].state
  if state == "completed":
    raise TestCommandError("completed issue requires explicit reopening before new completion")
  if state == "aborted":
    raise TestCommandError("aborted issue must be restarted before completion")
  # The caller has already validated the exact candidate and its test evidence.
  store.set_state(plan["issue"], "completed", tickets.revision)
  paths = [".repoworkflow/tickets.csv"]
  git(root, "add", "--force", "--", *paths)
  commit_owned_files(root, paths, f"workflow: complete issue {plan['issue']}")
  return git(root, "rev-parse", "HEAD").stdout.strip()


def dispatch_done(root: Path, plan: dict) -> dict:
  """Request the repository's ordinary GitHub CI worker.

  Parameters
  ----------
  root : Path
      Repository checkout.
  plan : dict
      Submission metadata supplied to CI.

  Returns
  -------
  dict
      Submitted disposition; dispatch does not claim tests or merge succeeded.
  """
  from adapters.repo_host_github_provider import GitHubBackend
  GitHubBackend(plan["repository"]).dispatch_workflow("prelim-done.yml",
    plan["prelim_ref"].removeprefix("refs/heads/"),
    {"prelim_ref": plan["prelim_ref"]})
  return {"status": "submitted", "prelim_ref": plan["prelim_ref"], "worker": "prelim-done.yml"}
