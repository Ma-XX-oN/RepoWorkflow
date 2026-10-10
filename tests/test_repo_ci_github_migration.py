import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.repo_ci_github_provider import handle_request


ROOT = Path(__file__).resolve().parents[1]


def request(operation, inputs=None, artifacts=None):
  return {
    "contract_version": 1,
    "operation": operation,
    "invocation_id": "invocation-67",
    "candidate": {
      "repository": "owner/repo", "commit": "a" * 40, "base": "b" * 40,
    },
    "requirements": {
      "stages": [], "capabilities": [], "artifacts": artifacts or [],
    },
    "inputs": inputs if inputs is not None else {},
  }


class RepoCiGithubMigrationTests(unittest.TestCase):
  def test_event_mapping_and_identity(self):
    value = request("inspect-context", {"event": "pull_request", "platform": "linux"})
    result = handle_request(value, ROOT)
    self.assertEqual(result["status"], "ok")
    self.assertEqual(result["candidate"], value["candidate"])
    self.assertEqual(result["invocation_id"], value["invocation_id"])
    self.assertEqual(result["observations"]["mode"], "automatic")

  def test_missing_capability_fails_closed(self):
    value = request("resolve-capabilities", {"platform": "linux"})
    value["requirements"]["capabilities"] = ["unavailable-capability"]
    result = handle_request(value, ROOT)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "capability-unavailable")

  def test_execute_missing_declaration_never_emits_success(self):
    result = handle_request(request("execute"), ROOT)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "invalid-request")
    self.assertEqual(result["artifacts"], [])

  def test_execute_requires_exact_checkout_and_base(self):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    value = request("execute")
    value["requirements"]["stages"] = ["validation"]
    value["inputs"] = {"base": value["candidate"]["base"],
                       "stage_groups": {"validation": "invariant-self-ci-contract"}}
    mismatch = handle_request(value, ROOT)
    self.assertEqual(mismatch["diagnostics"][0]["code"], "identity-mismatch")
    value["candidate"]["commit"] = head
    value["inputs"]["base"] = "stale"
    mismatch = handle_request(value, ROOT)
    self.assertEqual(mismatch["diagnostics"][0]["code"], "identity-mismatch")

  def test_execute_rejects_missing_or_duplicate_stage_groups(self):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    value = request("execute", {"base": "b" * 40, "stage_groups": {}})
    value["candidate"]["commit"] = head
    value["requirements"]["stages"] = ["required"]
    result = handle_request(value, ROOT)
    self.assertEqual(result["diagnostics"][0]["code"], "invalid-request")
    value["requirements"]["stages"] = ["required", "required"]
    value["inputs"]["stage_groups"] = {"required": "invariant-self-ci-contract"}
    result = handle_request(value, ROOT)
    self.assertEqual(result["diagnostics"][0]["code"], "invalid-request")

  def test_execute_preflights_all_stages_before_process_runs(self):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    value = request("execute")
    value["candidate"]["commit"] = head
    value["requirements"]["stages"] = ["available", "missing"]
    value["inputs"] = {
      "base": value["candidate"]["base"],
      "stage_groups": {
        "available": "invariant-self-ci-contract",
        "missing": "group-not-in-catalogue",
      },
    }
    with patch("repo_workflow.repo_ci_github_provider.subprocess.run") as run:
      run.side_effect = [subprocess.CompletedProcess([], 0, head, "")]
      result = handle_request(value, ROOT)
      self.assertEqual(run.call_count, 1)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "prerequisite-unavailable")

  def test_execute_reports_genuine_process_result_without_classification(self):
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    value = request("execute")
    value["candidate"]["commit"] = head
    value["requirements"]["stages"] = ["selected"]
    value["inputs"] = {"base": value["candidate"]["base"],
                       "stage_groups": {"selected": "invariant-self-ci-contract"}}
    with patch("repo_workflow.repo_ci_github_provider.subprocess.run") as run:
      run.side_effect = [
        subprocess.CompletedProcess([], 0, head + "\n", ""),
        subprocess.CompletedProcess([], 1, b"", b"test failed"),
      ]
      result = handle_request(value, ROOT)
    self.assertEqual(result["status"], "ok")
    self.assertEqual(result["observations"]["stages"][0]["outcome"], "failed")
    self.assertEqual(result["observations"]["stages"][0]["exit_code"], 1)
    self.assertNotIn("classification", result["observations"])

  def test_consumer_execute_preserves_core_statuses_and_evidence(self):
    from tests.support import RepoFixture

    for rc, status in ((0, "PASS"), (7, "FAIL"), (2, "INCOMPLETE")):
      with self.subTest(status=status), tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "consumer"
        workspace.mkdir()
        fixture = RepoFixture(workspace, validation_body=f"raise SystemExit({rc})\n")
        destination = Path(td) / "observations" / "local.json"
        value = request("execute")
        value["candidate"]["commit"] = fixture.head()
        value["requirements"]["stages"] = ["local"]
        value["inputs"] = {
          "consumer_workspace": str(workspace),
          "result_path": str(destination),
          "mode": "development",
          "base": value["candidate"]["base"],
        }
        with patch.dict(os.environ, {
          "RWF_REPO_CI_WORKSPACE": str(workspace),
          "RWF_REPO_CI_RESULT_ROOT": str(destination.parent),
          "GITHUB_REPOSITORY": "owner/repo",
        }):
          result = handle_request(value, ROOT)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["candidate"], value["candidate"])
        self.assertEqual(result["observations"]["stages"][0]["core_result"]["status"],
                         status, result["observations"]["stages"][0]["core_result"])
        self.assertEqual(json.loads(destination.read_text())["status"], status)
        self.assertEqual(
          result["observations"]["stages"][0]["core_exit_code"],
          0 if status == "PASS" else 1 if status == "FAIL" else 2,
        )

  def test_stable_consumer_execution_remains_core_authoritative(self):
    from tests.support import RepoFixture

    with tempfile.TemporaryDirectory() as td:
      workspace = Path(td) / "consumer"
      workspace.mkdir()
      fixture = RepoFixture(workspace, version="1.2.3")
      destination = Path(td) / "results" / "stable.json"
      value = request("execute")
      value["candidate"]["commit"] = fixture.head()
      value["requirements"]["stages"] = ["local"]
      value["inputs"] = {
        "consumer_workspace": str(workspace),
        "result_path": str(destination),
        "mode": "stable",
        "base": value["candidate"]["base"],
      }
      env = {
        "RWF_REPO_CI_WORKSPACE": str(workspace),
        "RWF_REPO_CI_RESULT_ROOT": str(destination.parent),
        "GITHUB_REPOSITORY": "owner/repo",
      }
      with patch.dict(os.environ, env):
        result = handle_request(value, ROOT)
      self.assertEqual(result["status"], "ok", result)
      self.assertEqual(result["observations"]["stages"][0]["core_result"]["status"],
                       "PASS")
      self.assertEqual(json.loads(destination.read_text())["version"], "1.2.3")
      self.assertNotIn("terminal_classification", result["observations"])

  @unittest.skipIf(os.name == "nt", "symlinked hosted consumer fixture is POSIX-only")
  def test_consumer_dispatcher_roundtrip_uses_installed_provider(self):
    from tests.support import RepoFixture

    with tempfile.TemporaryDirectory() as td:
      workspace = Path(td) / "consumer"
      workspace.mkdir()
      (workspace / "RepoWorkflow").symlink_to(ROOT, target_is_directory=True)
      fixture = RepoFixture(workspace)
      result_dir = Path(td) / "outputs"
      value = request("execute")
      value["candidate"]["commit"] = fixture.head()
      value["requirements"]["stages"] = ["local"]
      value["inputs"] = {
        "consumer_workspace": str(workspace),
        "result_path": str(result_dir / "local.json"),
        "mode": "development",
        "base": value["candidate"]["base"],
      }
      env = {
        **os.environ,
        "GITHUB_REPOSITORY": "owner/repo",
        "RWF_REPO_CI_WORKSPACE": str(workspace),
        "RWF_REPO_CI_RESULT_ROOT": str(result_dir),
      }
      completed = subprocess.run(
        [sys.executable, str(ROOT / "repo_workflow.py"), "repo-ci", "execute"],
        input=json.dumps(value), cwd=workspace, env=env, text=True,
        capture_output=True, check=False, timeout=60,
      )
      self.assertEqual(completed.returncode, 0, completed.stderr)
      result = json.loads(completed.stdout)
      self.assertEqual(result["status"], "ok", result)
      self.assertEqual(result["candidate"], value["candidate"])
      self.assertEqual(result["observations"]["stages"][0]["core_result"]["status"],
                       "PASS")
      self.assertEqual(json.loads((result_dir / "local.json").read_text())["status"],
                       "PASS")
      event = Path(td) / "event.json"
      event.write_text("{}")
      env.update({
        "RWF_CI_BASE_SHA": value["candidate"]["base"],
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_PATH": str(event),
      })
      executable = str(ROOT / "repo_workflow" / "repo_ci_github_machine.py")
      for subcommand, expected in (
        ("mode", "development"),
        ("matrix", {"include": [{
          "id": "local", "runner": "ubuntu-latest",
          "nodeVersion": "", "pythonVersion": "3.13",
        }]}),
        ("prepare-context", {
          "runner": "ubuntu-latest", "nodeVersion": "",
          "pythonVersion": "3.13",
        }),
      ):
        with self.subTest(machine_command=subcommand):
          args = [sys.executable, executable, subcommand]
          if subcommand == "mode":
            args.extend([
              "--event-name", "workflow_dispatch",
              "--event-path", str(event), "--branch", "issue-1-test",
            ])
          completed = subprocess.run(
            args, cwd=workspace, env=env, capture_output=True,
            text=True, check=False, timeout=30,
          )
          self.assertEqual(completed.returncode, 0, completed.stderr)
          actual = (completed.stdout.strip() if subcommand == "mode"
                    else json.loads(completed.stdout))
          self.assertEqual(actual, expected)

  def test_consumer_execute_rejects_changed_identity_and_unsafe_result(self):
    from tests.support import RepoFixture

    with tempfile.TemporaryDirectory() as td:
      workspace = Path(td) / "consumer"
      workspace.mkdir()
      fixture = RepoFixture(workspace)
      destination = Path(td) / "observations" / "local.json"
      value = request("execute")
      value["candidate"]["commit"] = fixture.head()
      value["requirements"]["stages"] = ["local"]
      value["inputs"] = {
        "consumer_workspace": str(workspace),
        "result_path": str(destination),
        "mode": "development",
        "base": value["candidate"]["base"],
      }
      env = {
        "RWF_REPO_CI_WORKSPACE": str(workspace),
        "RWF_REPO_CI_RESULT_ROOT": str(destination.parent),
      }
      with patch.dict(os.environ, env):
        wrong = json.loads(json.dumps(value))
        wrong["candidate"]["commit"] = "f" * 40
        self.assertEqual(handle_request(wrong, ROOT)["diagnostics"][0]["code"],
                         "identity-mismatch")
        wrong = json.loads(json.dumps(value))
        wrong["inputs"]["result_path"] = str(Path(td) / "outside.json")
        self.assertEqual(handle_request(wrong, ROOT)["diagnostics"][0]["code"],
                         "invalid-request")
        wrong = json.loads(json.dumps(value))
        wrong["inputs"]["base"] = "wrong"
        self.assertEqual(handle_request(wrong, ROOT)["diagnostics"][0]["code"],
                         "identity-mismatch")
        self.assertFalse(destination.exists())

  def test_consumer_machine_outputs_equal_legacy_adapter(self):
    from tests.support import RepoFixture
    from repo_workflow.repo_ci_github_compat import (
      github_matrix, github_mode, github_prepare_context, load_github_config,
    )
    from repo_workflow.config import load_config

    with tempfile.TemporaryDirectory() as td:
      workspace = Path(td) / "consumer"
      workspace.mkdir()
      fixture = RepoFixture(workspace)
      event = Path(td) / "event.json"
      event.write_text("{}")
      env = {
        "RWF_REPO_CI_WORKSPACE": str(workspace),
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_PATH": str(event),
      }
      with patch.dict(os.environ, env):
        mode = request("inspect-context", {
          "consumer_workspace": str(workspace), "legacy": "mode",
          "event_name": "workflow_dispatch", "event_path": str(event),
          "branch": "issue-1-test",
        })
        mode["candidate"]["commit"] = fixture.head()
        observed = handle_request(mode, ROOT)
        self.assertEqual(observed["status"], "ok", observed)
        self.assertEqual(
          observed["observations"]["legacy_output"],
          github_mode(workspace, "workflow_dispatch", event, "issue-1-test", "main"),
        )
        for operation, legacy, expected in (
          ("resolve-capabilities", "matrix",
           github_matrix(load_config(workspace), load_github_config(workspace))),
          ("prepare", "prepare-context",
           github_prepare_context(load_config(workspace), load_github_config(workspace))),
        ):
          with self.subTest(operation=operation):
            value = request(operation, {
              "consumer_workspace": str(workspace), "legacy": legacy,
            })
            value["candidate"]["commit"] = fixture.head()
            observed = handle_request(value, ROOT)
            self.assertEqual(observed["status"], "ok", observed)
            self.assertEqual(observed["observations"]["legacy_output"], expected)

  def test_legacy_machine_context_rejects_unbound_workspace(self):
    value = request("resolve-capabilities", {
      "consumer_workspace": "/untrusted", "legacy": "matrix",
    })
    result = handle_request(value, ROOT)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "prerequisite-unavailable")

  def test_consumer_workflow_routes_validation_but_keeps_core_finalizer(self):
    workflow = (ROOT / ".github" / "workflows" / "consumer-ci.yml").read_text()
    self.assertIn("repo-ci\", \"execute", workflow)
    self.assertIn("RWF_REPO_CI_WORKSPACE", workflow)
    self.assertIn("repo_ci_github_machine.py mode", workflow)
    self.assertIn("repo_ci_github_machine.py matrix", workflow)
    self.assertIn("repo_ci_github_machine.py prepare-context", workflow)
    self.assertIn("python RepoWorkflow/repo_workflow.py finalize", workflow)
    self.assertIn("python RepoWorkflow/repo_workflow.py stable-finalize", workflow)

  def test_publish_fetch_integrity_and_identity(self):
    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      (root / "input").mkdir()
      (root / "input" / "result").write_bytes(b"failed-test-observation")
      with patch.dict(os.environ, {"RWF_REPO_CI_TRANSPORT_ROOT": td}):
        publication = request("publish", {"source_dir": "input",
                                           "destination_dir": "bundle"}, ["result"])
        self.assertEqual(handle_request(publication, ROOT)["status"], "ok")
        retrieval = request("fetch", {"source_dir": "bundle",
                                      "destination_dir": "output"}, ["result"])
        self.assertEqual(handle_request(retrieval, ROOT)["status"], "ok")
        self.assertEqual((root / "output" / "result").read_bytes(),
                         b"failed-test-observation")
        swapped = request("fetch", {"source_dir": "bundle",
                                    "destination_dir": "stale"}, ["result"])
        swapped["candidate"]["base"] = "c" * 40
        rejected = handle_request(swapped, ROOT)
        self.assertEqual(rejected["status"], "error")
        self.assertEqual(rejected["diagnostics"][0]["code"], "identity-mismatch")
        self.assertFalse((root / "stale").exists())
        (root / "bundle" / "result").write_bytes(b"passed")
        corrupt = handle_request(request("fetch", {"source_dir": "bundle",
                                                    "destination_dir": "tampered"},
                                          ["result"]), ROOT)
        self.assertEqual(corrupt["diagnostics"][0]["code"], "integrity-failed")
        self.assertFalse((root / "tampered").exists())

  def test_transport_workspace_escape_rejected(self):
    with tempfile.TemporaryDirectory() as td:
      with patch.dict(os.environ, {"RWF_REPO_CI_TRANSPORT_ROOT": td}):
        result = handle_request(request("publish", {
          "source_dir": "../outside", "destination_dir": "bundle",
        }), ROOT)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["artifacts"], [])

  def test_policy_failure_is_observation_not_terminal_status(self):
    result = handle_request(request("check-policy", {"policies": []}), ROOT)
    self.assertEqual(result["status"], "error")
    self.assertEqual(result["diagnostics"][0]["code"], "invalid-request")

  def test_legacy_github_machine_boundary_preserves_adapter_results(self):
    from repo_workflow import github_adapter as old
    from repo_workflow import repo_ci_github_compat as compat

    with tempfile.TemporaryDirectory() as td:
      root = Path(td)
      event = root / "event.json"
      event.write_text(json.dumps({"before": "a" * 40, "after": "b" * 40}))
      self.assertEqual(
        compat.request_changed(root, "workflow_dispatch", event),
        old.request_changed(root, "workflow_dispatch", event),
      )
      for name, branch in (("workflow_dispatch", "feature"), ("push", "main"),
                           ("pull_request", "feature")):
        with self.subTest(event=name, branch=branch):
          self.assertEqual(
            compat.github_mode(root, name, event, branch, "main"),
            old.github_mode(root, name, event, branch, "main"),
          )
      settings = {"schema": 1, "runners": {"linux": "ubuntu-latest"},
                  "prepareRunner": "ubuntu-latest"}
      config = {"environments": [{"id": "linux"}], "artifacts": []}
      self.assertEqual(compat.github_matrix(config, settings),
                       old.github_matrix(config, settings))
      self.assertEqual(compat.github_prepare_context(config, settings),
                       old.github_prepare_context(config, settings))
      self.assertEqual(compat.github_prepare_runner(settings),
                       old.github_prepare_runner(settings))

  def test_public_machine_commands_import_provider_boundary(self):
    source = (ROOT / "repo_workflow.py").read_text()
    self.assertIn("from repo_workflow.repo_ci_github_compat import (", source)
    self.assertNotIn("from repo_workflow.github_adapter import (", source)

  def test_dispatcher_routes_through_configured_github_provider(self):
    value = request("inspect-context", {"event": "workflow_dispatch",
                                         "platform": "linux"})
    completed = subprocess.run(
      [sys.executable, "-m", "repo_workflow.repo_ci_dispatcher", "inspect-context"],
      input=json.dumps(value), capture_output=True, text=True, cwd=ROOT,
    )
    self.assertEqual(completed.returncode, 0, completed.stderr)
    response = json.loads(completed.stdout)
    self.assertEqual(response["observations"]["mode"], "manual")
    self.assertEqual(response["candidate"], value["candidate"])


if __name__ == "__main__":
  unittest.main()
