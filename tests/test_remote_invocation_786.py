"""#786 CMD wrapper tests: real Git ancestry, output, parity and denial."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.remote_invocation import (
  RemoteInvocationError,
  invoke_numbered,
)


def _run(root: Path, *args: str) -> str:
  proc = subprocess.run(
    ["git", *args], cwd=root, capture_output=True, text=True, check=False,
  )
  if proc.returncode:
    raise AssertionError(f"git {args}: {proc.stderr}")
  return proc.stdout.strip()


class CmdFixture(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.area = Path(self.temp.name)
    self.remote = self.area / "remote.git"
    self.repo = self.area / "repo"
    self.repo.mkdir()
    self.branch = "issue-786-fixture"
    self.cmd = "CMD-1-" + self.branch
    _run(self.area, "init", "--bare", str(self.remote))
    _run(self.repo, "init", "-b", self.branch)
    _run(self.repo, "config", "user.name", "RWF Test")
    _run(self.repo, "config", "user.email", "rwf-test@example.invalid")
    _run(self.repo, "remote", "add", "origin", str(self.remote))
    (self.repo / "README.md").write_text("source\n", encoding="utf-8")
    _run(self.repo, "add", "README.md")
    _run(self.repo, "commit", "-m", "source")
    self.source_sha = _run(self.repo, "rev-parse", "HEAD")
    _run(self.repo, "push", "origin", self.branch)
    _run(self.repo, "checkout", "-b", self.cmd)
    self.marker("test RED --remote 0")
    self.push()
    self.hosted = patch.dict(os.environ, {"RWF_HOSTED_INVOCATION": "1"})
    self.hosted.start()
    self.addCleanup(self.hosted.stop)

  def marker(self, text: str):
    path = self.repo / ".ci" / "rwf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    _run(self.repo, "add", ".ci/rwf")
    _run(self.repo, "commit", "-m", "request")

  def push(self):
    _run(self.repo, "push", "origin", self.cmd)

  def invoke(self, *args: str, handler=None):
    return invoke_numbered(
      self.repo, list(args or ("test", "RED", "--remote", "0")),
      handler or (lambda root, words: 0),
    )

  def test_valid_request_uses_source_checkout_and_identical_argv(self):
    seen = []
    def command(root, argv):
      seen.append((
        _run(root, "branch", "--show-current"),
        _run(root, "rev-parse", "HEAD"),
        list(argv),
      ))
      print("snowman: ☃")
      return 0
    outcome = self.invoke(handler=command)
    self.assertEqual(seen, [(self.branch, self.source_sha, ["test", "RED"])])
    self.assertEqual(outcome.exit_code, 0)
    self.assertEqual(outcome.stdout, "snowman: ☃\n")
    self.assertEqual(outcome.stderr, "")
    self.assertEqual(outcome.source_sha, self.source_sha)
    self.assertEqual(outcome.retry, 0)

  def test_nonzero_and_exception_capture(self):
    def fail(root, args):
      print("failure: λ")
      print("stderr: Δ", file=__import__("sys").stderr)
      return 37
    outcome = self.invoke(handler=fail)
    self.assertEqual(outcome.exit_code, 37)
    self.assertEqual(outcome.stdout, "failure: λ\n")
    self.assertEqual(outcome.stderr, "stderr: Δ\n")
    self.assertEqual(outcome.output, "failure: λ\nstderr: Δ\n")
    def crash(root, args):
      raise RuntimeError("deliberate explosion")
    failure = self.invoke(handler=crash)
    self.assertEqual(failure.exit_code, 1)
    self.assertIn("RuntimeError: deliberate explosion", failure.stderr)

  def test_public_runtime_parity_for_red_without_selection(self):
    import importlib.util
    engine = Path(__file__).resolve().parents[1] / "repo_workflow.py"
    spec = importlib.util.spec_from_file_location("rwf_786_entry", engine)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as localdir:
      local = Path(localdir) / "source"
      _run(self.area, "clone", "--quiet", str(self.repo), str(local))
      _run(local, "checkout", "-b", self.branch, self.source_sha)
      localout, localerr = io.StringIO(), io.StringIO()
      with redirect_stdout(localout), redirect_stderr(localerr):
        localstatus = module.main(["--root", str(local), "test", "RED"])
      wrappedout, wrappederr = io.StringIO(), io.StringIO()
      with redirect_stdout(wrappedout), redirect_stderr(wrappederr):
        wrappedstatus = module.main([
          "--root", str(self.repo), "test", "RED", "--remote", "0",
        ])
      self.assertEqual((wrappedstatus, wrappedout.getvalue(), wrappederr.getvalue()),
                       (localstatus, localout.getvalue(), localerr.getvalue()))

  def test_ordinary_branch_numbered_invocation_is_denied(self):
    _run(self.repo, "checkout", self.branch)
    with self.assertRaisesRegex(RemoteInvocationError, "CMD-N-source"):
      self.invoke()

  def test_missing_hosted_context_denied(self):
    with patch.dict(os.environ, {"RWF_HOSTED_INVOCATION": ""}):
      with self.assertRaisesRegex(RemoteInvocationError, "hosted"):
        self.invoke()

  def test_retry_suffix_must_match_latest_marker(self):
    with self.assertRaisesRegex(RemoteInvocationError, "mismatch"):
      self.invoke("test", "RED", "--remote", "1")
    for suffix in ("-1", "01", "none"):
      with self.subTest(suffix=suffix):
        with self.assertRaisesRegex(RemoteInvocationError, "invalid"):
          self.invoke("test", "RED", "--remote", suffix)

  def test_changed_request_argv_denied(self):
    with self.assertRaisesRegex(RemoteInvocationError, "mismatch"):
      self.invoke("test", "GREEN", "--remote", "0")

  def test_unauthorized_request_commit_paths_denied(self):
    (self.repo / "unexpected").write_text("changed", encoding="utf-8")
    _run(self.repo, "add", "unexpected")
    _run(self.repo, "commit", "-m", "rogue")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "unauthorized"):
      self.invoke()

  def test_result_commit_prevents_reexecution(self):
    path = self.repo / ".repoworkflow" / "result"
    path.parent.mkdir(parents=True)
    path.write_text("0\n", encoding="utf-8")
    _run(self.repo, "add", ".repoworkflow/result")
    _run(self.repo, "commit", "-m", "published")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "already has a result"):
      self.invoke()

  def test_stale_checkout_denied_before_handler(self):
    self.marker("test RED --remote 1")
    ran = []
    with self.assertRaisesRegex(RemoteInvocationError, "stale"):
      self.invoke(handler=lambda r, a: ran.append(1))
    self.assertEqual(ran, [])

  def test_retry_chain_and_stale_attempt_denial(self):
    self.marker("test RED --remote 1")
    self.push()
    outcome = self.invoke("test", "RED", "--remote", "1")
    self.assertEqual(outcome.retry, 1)
    with self.assertRaisesRegex(RemoteInvocationError, "mismatch"):
      self.invoke("test", "RED", "--remote", "0")
    self.marker("test RED --remote 3")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "lineage"):
      self.invoke("test", "RED", "--remote", "3")

  def test_malformed_quoting_rejected_before_handler(self):
    self.marker("test 'RED --remote 1")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "quoting"):
      self.invoke("test", "RED", "--remote", "1")

  def test_noncanonical_marker_is_denied(self):
    self.marker("test   RED --remote 1")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "noncanonical"):
      self.invoke("test", "RED", "--remote", "1")

  def test_non_utf8_marker_is_denied(self):
    (self.repo / ".ci" / "rwf").write_bytes(b"test RED --remote 1\xff")
    _run(self.repo, "add", ".ci/rwf")
    _run(self.repo, "commit", "-m", "broken encoding")
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "UTF-8"):
      self.invoke("test", "RED", "--remote", "1")


  def alternate_request(self, text: str):
    self.cmd = "CMD-2-" + self.branch
    _run(self.repo, "checkout", "-b", self.cmd, self.source_sha)
    self.marker(text)
    self.push()

  def test_unsupported_hosted_grammar_rejected(self):
    self.alternate_request("version --remote 0")
    with self.assertRaisesRegex(RemoteInvocationError, "not eligible"):
      self.invoke("version", "--remote", "0")

  def test_read_only_results_rejected(self):
    self.alternate_request("test results --remote 0")
    with self.assertRaisesRegex(RemoteInvocationError, "read-only"):
      self.invoke("test", "results", "--remote", "0")

  def test_real_cli_nonzero_parity(self):
    import importlib.util
    self.alternate_request("test temporary --remote 0")
    script = Path(__file__).resolve().parents[1] / "repo_workflow.py"
    spec = importlib.util.spec_from_file_location("rwf_786_failure", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as localdir:
      source = Path(localdir) / "source"
      _run(self.area, "clone", "--quiet", str(self.repo), str(source))
      _run(source, "checkout", "-b", self.branch, self.source_sha)
      out1, err1 = io.StringIO(), io.StringIO()
      with redirect_stdout(out1), redirect_stderr(err1):
        rc1 = module.main(["--root", str(source), "test", "temporary"])
      out2, err2 = io.StringIO(), io.StringIO()
      with redirect_stdout(out2), redirect_stderr(err2):
        rc2 = module.main([
          "--root", str(self.repo), "test", "temporary", "--remote", "0",
        ])
      self.assertNotEqual(rc1, 0)
      self.assertEqual(rc2, rc1)
      self.assertEqual(out2.getvalue(), out1.getvalue())
      self.assertIn("missing test catalogue:", err1.getvalue())
      self.assertIn("missing test catalogue:", err2.getvalue())

  def test_published_previous_attempt_is_valid_retry_ancestry(self):
    path = self.repo / ".repoworkflow" / "result"
    path.parent.mkdir(parents=True)
    path.write_text("1\nold outcome\n", encoding="utf-8")
    _run(self.repo, "add", ".repoworkflow/result")
    _run(self.repo, "commit", "-m", "publish previous attempt")
    self.marker("test RED --remote 1")
    self.push()
    self.assertEqual(self.invoke("test", "RED", "--remote", "1").retry, 1)

if __name__ == "__main__":
  unittest.main()
