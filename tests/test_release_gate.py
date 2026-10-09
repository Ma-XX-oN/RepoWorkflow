from pathlib import Path
import runpy
import subprocess
import shutil
import unittest

GATE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "release-gate.py"))
release_tier = GATE["release_tier"]
PLATFORMS = GATE["PLATFORMS"]
MATRICES = GATE["MATRICES"]

def jobs(tier="integration"):
  data = {"classify": "success", "plan": "success", "issue-validate": "skipped"}
  data["validate"] = "success" if tier == "integration" else "skipped"
  for prefix in MATRICES:
    if tier == "docs":
      data[prefix + " ($" + "{{ matrix.os }})"] = "skipped"
    else:
      for os_name in PLATFORMS:
        data[f"{prefix} ({os_name})"] = "success"
  return data

def lines(data):
  return [f"{name}\t{status}\n" for name, status in data.items()]

class ReleaseGateTests(unittest.TestCase):
  def test_release_shell_parses(self):
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "stable-release.yml"
    content = path.read_text(encoding="utf-8")
    marker = "        run: |\\n"
    self.assertEqual(content.count(marker), 1)
    script = content.split(marker, 1)[1]
    self.assertTrue(script.startswith("          set -euo pipefail"))
    if shutil.which("bash") is None:
      self.skipTest("bash executable unavailable")
    result = subprocess.run(
      ["bash", "-n"], input=script, text=True, capture_output=True,
      check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_integration_and_docs_pass(self):
    self.assertEqual(release_tier(lines(jobs())), "integration")
    self.assertEqual(release_tier(lines(jobs("docs"))), "docs")

  def test_missing_duplicate_and_invalid_job_fail(self):
    base = jobs()
    del base["plan"]
    with self.assertRaises(ValueError):
      release_tier(lines(base))
    with self.assertRaises(ValueError):
      release_tier(lines(jobs()) + ["plan\tsuccess\n"])
    with self.assertRaises(ValueError):
      release_tier(["invalid\n"])

  def test_failure_and_incomplete_matrix_fail(self):
    for status in ("failure", "cancelled", "skipped", "timed_out"):
      base = jobs()
      base["validate"] = status
      with self.assertRaises(ValueError):
        release_tier(lines(base))
    base = jobs()
    del base["Probe argv limits (windows-latest)"]
    with self.assertRaises(ValueError):
      release_tier(lines(base))
    base = jobs()
    base["Probe graph renderer (macos-latest)"] = "failure"
    with self.assertRaises(ValueError):
      release_tier(lines(base))
    base = jobs()
    base["Probe argv limits (other)"] = "success"
    with self.assertRaises(ValueError):
      release_tier(lines(base))

  def test_docs_wrong_matrix_and_issue_run_fail(self):
    base = jobs("docs")
    base["issue-validate"] = "success"
    with self.assertRaises(ValueError):
      release_tier(lines(base))
    base = jobs("docs")
    base["Probe ticket merge ($" + "{{ matrix.os }})"] = "success"
    with self.assertRaises(ValueError):
      release_tier(lines(base))
    base = jobs("docs")
    del base["Probe graph renderer ($" + "{{ matrix.os }})"]
    with self.assertRaises(ValueError):
      release_tier(lines(base))

if __name__ == "__main__":
  unittest.main()
