from pathlib import Path
import subprocess
import tempfile
import unittest

from repo_workflow.ci_invocation import (
  CiInvocationError,
  parse_invocation,
  verify_invocation,
)


class CiInvocationTests(unittest.TestCase):
  def test_all_five_stages_are_recognised(self):
    for stage in (
      "RED-testing",
      "temp-testing",
      "GREEN-testing",
      "regression-testing",
      "integration-testing",
    ):
      with self.subTest(stage=stage):
        request = parse_invocation(stage + " " + "a" * 40 + "\n")
        self.assertEqual((request.stage, request.previous_tip), (
          stage, "a" * 40,
        ))

  def test_unknown_stage_rejected(self):
    for stage in ("", "no-CI-invocation", "regress-testing"):
      with self.subTest(stage=stage):
        with self.assertRaises(CiInvocationError):
          parse_invocation(stage + " " + "a" * 40)

  def test_noncanonical_sha_and_extra_data_rejected(self):
    values = (
      "RED-testing short",
      "RED-testing " + "A" * 40,
      "RED-testing " + "g" * 40,
      "RED-testing " + "a" * 40 + " extra",
      "RED-testing  " + "a" * 40,
      "RED-testing " + "a" * 40 + "\n\n",
    )
    for value in values:
      with self.subTest(value=value):
        with self.assertRaises(CiInvocationError):
          parse_invocation(value)

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = Path(self.tmp.name)
    self.git("init", "-q")
    self.git("config", "user.email", "ci@example.invalid")
    self.git("config", "user.name", "CI Fixture")
    (self.root / "source.py").write_text("x = 1\n")
    self.git("add", "source.py")
    self.git("commit", "-qm", "baseline")
    self.base = self.git("rev-parse", "HEAD")

  def tearDown(self):
    self.tmp.cleanup()

  def git(self, *args):
    return subprocess.check_output(
      ["git", "-C", str(self.root), *args],
      text=True,
    ).strip()

  def invoke(self, previous_tip=None, stage="regression-testing"):
    directory = self.root / ".ci"
    directory.mkdir(exist_ok=True)
    (directory / "run").write_text(
      f"{stage} {previous_tip or self.git('rev-parse', 'HEAD')}\n"
    )
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "invoke CI")

  def test_dedicated_request_committed_after_current_tip(self):
    self.invoke()
    self.assertEqual(verify_invocation(self.root).previous_tip, self.base)

  def test_retry_uses_previous_invocation_as_current_tip(self):
    self.invoke()
    missed_tip = self.git("rev-parse", "HEAD")
    self.invoke()
    self.assertEqual(verify_invocation(self.root).previous_tip, missed_tip)

  def test_stale_pre_invoke_sha_fails_closed(self):
    self.invoke(previous_tip="f" * 40)
    with self.assertRaisesRegex(CiInvocationError, "prior branch tip"):
      verify_invocation(self.root)

  def test_mixed_source_and_request_commit_fails_closed(self):
    (self.root / "source.py").write_text("x = 2\n")
    self.git("add", "source.py")
    self.invoke()
    with self.assertRaisesRegex(CiInvocationError, "only .ci/run"):
      verify_invocation(self.root)

  def test_uncommitted_marker_tamper_cannot_change_verified_request(self):
    self.invoke()
    committed = self.git("show", "HEAD:.ci/run")
    (self.root / ".ci" / "run").write_text(
      "RED-testing " + "f" * 40 + "\\n"
    )
    request = verify_invocation(self.root)
    self.assertEqual(request.stage, "regression-testing")
    self.assertEqual(
      committed.strip(),
      f"{request.stage} {request.previous_tip}",
    )

  def test_committed_marker_with_extra_newline_rejected(self):
    self.invoke()
    marker = self.root / ".ci" / "run"
    marker.write_text(marker.read_text() + "\\n")
    self.git("add", ".ci/run")
    self.git("commit", "-qm", "malformed marker")
    with self.assertRaises(CiInvocationError):
      verify_invocation(self.root)

  def test_no_request_fails_closed(self):
    with self.assertRaisesRegex(CiInvocationError, "missing"):
      verify_invocation(self.root)


if __name__ == "__main__":
  unittest.main()
