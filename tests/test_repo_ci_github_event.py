"""Black-box acceptance coverage for issue #92 adapter contract."""
import importlib.util
import pathlib
import subprocess
import sys
import json
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / "adapters" / "repo-ci-github-event.py"
SPEC = importlib.util.spec_from_file_location("repo_ci_github_event", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def request(operation="inspect-context", inputs=None, capabilities=None):
  return {
    "contract_version": 1,
    "operation": operation,
    "invocation_id": "attempt-1",
    "candidate": {"repository": "r", "commit": "candidate-1", "base": "base-1"},
    "requirements": {"stages": [], "capabilities": capabilities or [], "artifacts": []},
    "inputs": inputs if inputs is not None else {"event": "push", "platform": "linux"},
  }


class RepoCiGithubEventTests(unittest.TestCase):
  def test_supported_events_are_normalized(self):
    for event, expected in [
      ("push", "automatic"), ("pull_request", "automatic"),
      ("workflow_dispatch", "manual"), ("schedule", "scheduled"),
    ]:
      with self.subTest(event=event):
        got = MODULE.map_request(request(inputs={"event": event, "platform": "linux"}))
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["observations"]["mode"], expected)
        self.assertEqual(got["operation"], "inspect-context")
        self.assertEqual(got["candidate"]["commit"], "candidate-1")
        self.assertEqual(got["invocation_id"], "attempt-1")

  def test_platform_runner_mapping(self):
    for platform, runner in [
      ("linux", "ubuntu-latest"), ("windows", "windows-latest"),
      ("macos", "macos-latest"),
    ]:
      got = MODULE.map_request(request(inputs={"event": "push", "platform": platform}))
      self.assertEqual(got["observations"]["runner_ref"], runner)

  def test_capability_cardinality_and_prepare(self):
    for caps in ([], ["python"], ["python", "shell", "linux"]):
      with self.subTest(caps=caps):
        got = MODULE.map_request(request(
          "resolve-capabilities", {"platform": "linux"}, caps))
        self.assertEqual(got["status"], "ok")
        self.assertEqual(got["observations"]["unmet_requirements"], [])
    got = MODULE.map_request(request("prepare",
      {"event": "schedule", "platform": "windows"}, ["python", "windows"]))
    self.assertEqual(got["status"], "ok")
    self.assertTrue(got["observations"]["prepared"])

  def test_rejects_bad_envelope_and_conflicts(self):
    bad = []
    x = request(); x["contract_version"] = 2; bad.append((x, "unsupported-version"))
    x = request(); x["operation"] = "publish"; bad.append((x, "unsupported-operation"))
    x = request(); x["candidate"] = {}; bad.append((x, "invalid-request"))
    x = request(); x["operation"] = []; bad.append((x, "unsupported-operation"))
    x = request(capabilities=["gpu"]); bad.append((x, "capability-unavailable"))
    x = request(); del x["invocation_id"]; bad.append((x, "invalid-request"))
    x = request(); x["unexpected"] = True; bad.append((x, "invalid-request"))
    x = request(); x["requirements"]["capabilities"] = ["python", "python"]
    bad.append((x, "invalid-request"))
    x = request(inputs={"event": "push", "platform": "linux", "mode": "manual"})
    bad.append((x, "invalid-request"))
    x = request("resolve-capabilities", {"platform": "linux"}, ["gpu"])
    bad.append((x, "capability-unavailable"))
    x = request("resolve-capabilities",
      {"platform": "linux", "available_capabilities": ["windows"]})
    bad.append((x, "invalid-request"))
    for value, code in bad:
      with self.subTest(code=code, value=value):
        got = MODULE.map_request(value)
        self.assertEqual(got["status"], "error")
        self.assertEqual(got["diagnostics"][0]["code"], code)
        self.assertEqual(got["artifacts"], [])
        self.assertEqual(got["observations"], {})

  def test_malformed_types_fail_closed(self):
    for field, value in [
      ("event", []), ("event", {}), ("platform", []), ("platform", {}),
    ]:
      x = request()
      x["inputs"][field] = value
      got = MODULE.map_request(x)
      self.assertEqual(got["status"], "error")

  def test_execution_has_no_side_effects(self):
    run = subprocess.run([sys.executable, str(PATH)], input=json.dumps(
      request("prepare", {"event": "push", "platform": "linux"})),
      capture_output=True, text=True)
    self.assertEqual(run.returncode, 0, run.stderr)
    self.assertEqual(json.loads(run.stdout)["status"], "ok")
    run = subprocess.run([sys.executable, str(PATH)], input="{",
      capture_output=True, text=True)
    self.assertEqual(run.returncode, 2)
    self.assertEqual(json.loads(run.stdout)["diagnostics"][0]["code"], "invalid-request")


if __name__ == "__main__":
  unittest.main()
