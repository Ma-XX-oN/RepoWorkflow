"""RWF #702: RED catalogue completions, help parity, and real Bash Tab."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest

from tests import test_manual_test_cli as fixture


class RedCompletionCliTests(unittest.TestCase):
  def setUp(self):
    self.fx = fixture.TestManualLauncher("test_launcher_help_and_completion")
    self.fx.setUp()
    (self.fx.root / ".ci").mkdir(exist_ok=True)

  def tearDown(self):
    self.fx.tearDown()

  def groups(self, entries):
    declaration = {"test-harness": "unittest"}
    for name, description in entries:
      value = {"type": "regression", "name": "tests.test_manual_test_cli"}
      if description is not None:
        value["description"] = description
      declaration[name] = value
    catalogue = {
      "test-harnesses": {
        "unittest": {"command": "python", "layout": ["-m", "unittest", "$test"]}
      },
      "tests": [declaration],
    }
    (self.fx.root / ".ci/tests.json").write_text(
      json.dumps(catalogue), encoding="utf-8"
    )

  def check_error_parity(self, expected):
    responses = (
      self.fx.cli("test", "RED", "--help"),
      self.fx.cli("complete", "--describe", "test", "RED", ""),
      self.fx.cli("complete", "test", "RED", ""),
    )
    for observed in responses:
      self.assertEqual(observed.returncode, 2, observed)
      self.assertEqual(observed.stdout, "")
      self.assertIn(expected, observed.stderr)
    self.assertEqual(len({x.stderr for x in responses}), 1)

  def test_empty_other_issue_invalid_branch_and_catalogue(self):
    self.groups([])
    self.check_error_parity("RED/GREEN tests do not exist")
    self.groups([("issue-701-red-other", "different issue")])
    self.check_error_parity("RED/GREEN tests do not exist")
    self.fx.git("switch", "-c", "not-an-issue")
    self.check_error_parity("RED tests require a current started issue")
    self.fx.git("switch", "issue-702-test")
    (self.fx.root / ".ci/tests.json").write_text("{")
    self.check_error_parity("RED test catalogue is unavailable")

  def test_one_many_mixed_descriptions_prefix_and_ordering(self):
    for entries in (
      [("issue-702-red-single", None)],
      [("issue-702-red-z", "Zed"),
       ("issue-702-red-a", "Alpha descriptive text"),
       ("issue-702-red-m", None),
       ("issue-701-red-foreign", "Exclude me")],
    ):
      with self.subTest(entries=entries):
        self.groups(entries)
        expected = sorted(
          name for name, _ in entries if name.startswith("issue-702-")
        )
        candidates = self.fx.cli("complete", "test", "RED", "")
        self.assertEqual(candidates.returncode, 0, candidates.stderr)
        tokens = [x for x in candidates.stdout.splitlines()
                  if x.startswith("issue-")]
        self.assertEqual(tokens, expected)
        help_result = self.fx.cli("test", "RED", "--help")
        double = self.fx.cli("complete", "--describe", "test", "RED", "")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertEqual(double.returncode, 0, double.stderr)
        self.assertEqual(double.stdout, help_result.stdout)
        listing = [x for x in double.stdout.splitlines()
                   if x.startswith("issue-")]
        self.assertEqual(listing, [
          name + (" - " + description if description else "")
          for name, description in sorted(entries)
          if name.startswith("issue-702-")
        ])
        self.assertTrue(all(not x.endswith(" - ") for x in listing))
        narrowed = self.fx.cli("complete", "test", "RED", expected[0])
        self.assertEqual(narrowed.returncode, 0, narrowed.stderr)
        self.assertEqual(narrowed.stdout.splitlines(), [expected[0]])

  def _run_bash(self, body):
    if not shutil.which("bash"):
      self.skipTest("Bash not installed on this runner")

    def shell_path(path):
      if sys.platform != "win32":
        return str(path)
      import os
      converted = subprocess.run(
        ["bash", "-c", 'cygpath -u "$RWF_OS_PATH"'],
        env={**os.environ, "RWF_OS_PATH": str(path)},
        capture_output=True, text=True, check=False,
      )
      if converted.returncode:
        self.skipTest("Bash path translation unavailable")
      return converted.stdout.strip()

    wrapper = self.fx.engine / "red-rwf"
    entry = self.fx.engine / "repo_workflow.py"
    wrapper.write_text(
      "#!/usr/bin/env bash\nexec " + shlex.quote(shell_path(sys.executable))
      + " " + shlex.quote(shell_path(entry)) + ' "$@"\n',
      encoding="utf-8"
    )
    wrapper.chmod(0o755)
    source = fixture.SOURCE / "completions/repo-workflow.bash"
    script = (
      "source " + shlex.quote(shell_path(source)) + "\n"
      + 'COMP_WORDS=(rwf test RED "")\nCOMP_CWORD=3\n'
      + 'COMP_LINE="rwf test RED "\nCOMP_POINT=13\n'
      + body
    )
    import os
    return subprocess.run(
      ["bash", "-c", script], capture_output=True, text=True,
      env={**os.environ,
           "REPO_WORKFLOW_COMMAND": shell_path(wrapper),
           "REPO_WORKFLOW_ROOT": str(self.fx.root)},
      check=False,
    )

  def test_real_bash_single_and_double_tab_equals_help(self):
    self.groups([("issue-702-red-z", None),
                 ("issue-702-red-a", "A separate description")])
    observed = self._run_bash(
      '_repo_workflow_complete\n'
      + 'printf "ONE:%s\\n" "${COMPREPLY[@]}"\n'
      + '_repo_workflow_complete\n'
    )
    self.assertEqual(observed.returncode, 0,
                     repr(observed.stdout) + repr(observed.stderr))
    names = [line[4:] for line in observed.stdout.splitlines()
             if line.startswith("ONE:")]
    self.assertEqual(names, ["--remote", "issue-702-red-a", "issue-702-red-z"])
    rendered = "\n".join(line for line in observed.stdout.splitlines()
                         if not line.startswith("ONE:")) + "\n"
    self.assertEqual(rendered, self.fx.cli("test", "RED", "--help").stdout)

  def test_real_bash_error_is_not_suppressed(self):
    self.groups([])
    observed = self._run_bash(
      '_repo_workflow_complete\n_repo_workflow_complete\n'
      + 'printf "COUNT:%s\\n" "${#COMPREPLY[@]}"\n'
    )
    self.assertEqual(observed.returncode, 0,
                     repr(observed.stdout) + repr(observed.stderr))
    self.assertIn("COUNT:0", observed.stdout)
    self.assertGreaterEqual(
      observed.stderr.count("RED/GREEN tests do not exist"), 2
    )


if __name__ == "__main__":
  unittest.main()
