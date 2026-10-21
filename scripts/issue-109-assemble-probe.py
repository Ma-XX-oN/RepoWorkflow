"""Disposable exact-source assembly probe, never pushes or merges main."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


SOURCE = "49dcb20a7948b628a4eb1e6a8415f0b112dd5541"
DEPS = (
  ("#103", "d6acd97219ac45a90634d0a8c0b90780e9b7e5ff"),
  ("#681", "4938f73312691e7e593cd758965eb538f9e40baf"),
  ("#683", "ba3dde739701fcd358a01faf6f134078b0bf7924"),
)


def git(*args, check=True):
  result = subprocess.run(
    ["git", *args], capture_output=True, text=True, check=False)
  if check and result.returncode:
    raise RuntimeError(f"git {' '.join(args)}: {result.stderr}")
  return result


def stage_json(stage):
  return json.loads(git("show", f":{stage}:.ci/tests.json").stdout)


def union_catalogue():
  ours, theirs = stage_json(2), stage_json(3)
  if set(ours) != set(theirs):
    raise RuntimeError("catalogue top-level schema changed")
  for name in ("test-harnesses", "aliases"):
    for key, value in theirs[name].items():
      if key in ours[name] and ours[name][key] != value:
        raise RuntimeError(f"semantic catalogue {name} conflict: {key}")
      ours[name][key] = value
  existing = {}
  for group in ours["tests"]:
    for key, value in group.items():
      if key != "test-harness":
        existing[(group["test-harness"], key)] = value
  for group in theirs["tests"]:
    harness = group["test-harness"]
    for key, value in group.items():
      if key == "test-harness":
        continue
      identity = (harness, key)
      if identity in existing and existing[identity] != value:
        raise RuntimeError(f"semantic test conflict: {identity}")
      if identity not in existing:
        target = next((g for g in ours["tests"]
                       if g["test-harness"] == harness), None)
        if target is None:
          target = {"test-harness": harness}
          ours["tests"].append(target)
        target[key] = value
        existing[identity] = value
  Path(".ci/tests.json").write_text(
    json.dumps(ours, indent=2) + "\n", encoding="utf-8")
  git("add", ".ci/tests.json")
  print(f"Verified unique catalogue tests: {len(existing)}", flush=True)


def resolve_command_marker():
  pattern = re.compile(r"(regression-testing|integration-testing) [0-9a-f]{40}\n")
  values = [git("show", f":{n}:.ci/run").stdout for n in (2, 3)]
  if not all(pattern.fullmatch(v) for v in values):
    raise RuntimeError("unexpected persistent .ci/run contents")
  git("checkout", "--ours", "--", ".ci/run")
  git("add", ".ci/run")


def resolve_engine_version():
  versions = [git("show", f":{n}:.ci/engine-version").stdout
              for n in (2, 3)]
  # Issue #109 retains the exact assembled version authority. #683's
  # independent development version is a control-plane input, not a merge.
  expected = git("show", f"{SOURCE}:.ci/engine-version").stdout
  dependency = re.compile(r"0\.1\.122-issue\.683\.0\.[1-9][0-9]*\n")
  if versions[0] != expected or not dependency.fullmatch(versions[1]):
    raise RuntimeError(f"semantic version collision: {versions!r}")
  git("checkout", "--ours", "--", ".ci/engine-version")
  git("add", ".ci/engine-version")


def assemble():
  git("config", "user.name", "RWF isolated integration probe")
  git("config", "user.email", "rwf-probe@example.invalid")
  git("fetch", "--no-tags", "origin", SOURCE)
  git("checkout", "--detach", SOURCE)
  for label, sha in DEPS:
    print(f"Assembling {label} exact source {sha}", flush=True)
    git("fetch", "--no-tags", "origin", sha)
    merged = git("merge", "--no-ff", "--no-edit", sha, check=False)
    if merged.returncode:
      paths = git("diff", "--name-only", "--diff-filter=U").stdout
      conflicted = set(paths.splitlines())
      print(f"Explicit conflicts: {sorted(conflicted)}", flush=True)
      allowed = {".ci/tests.json", ".ci/run", ".ci/engine-version"}
      if not conflicted or conflicted - allowed:
        raise RuntimeError("unexpected non-control-plane source conflicts")
      if ".ci/tests.json" in conflicted:
        union_catalogue()
      if ".ci/run" in conflicted:
        resolve_command_marker()
      if ".ci/engine-version" in conflicted:
        resolve_engine_version()
      if git("diff", "--name-only", "--diff-filter=U").stdout.strip():
        raise RuntimeError("unresolved content conflict")
      git("commit", "--no-edit")
    print(f"Integrated {label}: {git('rev-parse','HEAD').stdout.strip()}",
          flush=True)
  if git("status", "--porcelain").stdout.strip():
    raise RuntimeError("dirty assembled source")
  print(f"FULLY ASSEMBLED TREE: {git('rev-parse','HEAD').stdout.strip()}",
        flush=True)
  subprocess.run(
    ["python", "-m", "unittest", "-v", "tests.test_done_executor",
     "tests.test_done_provider_acceptance", "tests.test_done_host_coordinator",
     "tests.test_done_provider_pipeline", "tests.test_done_retirement_bridge"],
    check=True)
  print("Executing strict #681 IntegrationHost transport interoperability",
        flush=True)
  import sys
  sys.path.insert(0, str(Path.cwd()))
  from repo_workflow.integration_host_v2 import IntegrationHost
  from tests.test_done_provider_pipeline import PipelineTests
  example = PipelineTests("test_one_ready_end_to_end_local_provider_simulation")
  example.setUp()
  backing = example.host
  readonly = {
    "refs.list", "destination.read", "lease.read", "attempt.read",
    "mit.deferred.read", "mit.resume.read",
  }
  def transport(request):
    op = request["operation"]
    params = request["parameters"]
    result = backing.request(op, request["request_id"], params)
    if op == "destination.read":
      result = {
        "destination": params["destination"],
        **result, "policy_present": False, "policy_text": None}
    return {
      "schema_version": 2, "repository": request["repository"],
      "operation": op, "request_id": request["request_id"],
      "status": "unchanged" if op in readonly else "applied",
      "result": result,
    }
  host = IntegrationHost("Org/Repo", transport)
  outcome = example.invoke(host=host)
  if (outcome.accepted.landed_sha != "d" * 40
      or backing.terminal["status"] != "integrated"
      or backing.lease["generation"] != 2):
    raise RuntimeError("provider-neutral v2 interoperation did not persist")
  print("STRICT V2 HOST INTEROP: PASS (simulated transport only)", flush=True)
  print("Running full assembled-source unittest regression", flush=True)
  subprocess.run(
    ["python", "-m", "unittest", "discover", "-s", "tests"], check=True)


if __name__ == "__main__":
  assemble()
