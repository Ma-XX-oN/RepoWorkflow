"""#786 CMD wrapper tests: real Git ancestry, output, parity and denial."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.remote_invocation import (
  InvocationOutcome,
  RemoteInvocationError,
  emit_outcome,
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
    self.hosted = patch.dict(os.environ, {
      "RWF_HOSTED_INVOCATION": "1",
      "GIT_AUTHOR_NAME": "RWF Test",
      "GIT_AUTHOR_EMAIL": "rwf-test@example.invalid",
      "GIT_COMMITTER_NAME": "RWF Test",
      "GIT_COMMITTER_EMAIL": "rwf-test@example.invalid",
    })
    self.hosted.start()
    self.addCleanup(self.hosted.stop)

  def marker(self, text: str, *, source_identity: str | None = None):
    path = self.repo / ".ci" / "rwf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    _run(self.repo, "add", ".ci/rwf")
    _run(
      self.repo, "commit", "-m", "request", "-m",
      "RWF-Source: " + (source_identity or self.source_sha),
    )

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
    engine = Path(__file__).resolve().parents[1] / "repo_workflow.py"
    with tempfile.TemporaryDirectory() as localdir:
      local = Path(localdir) / "source"
      _run(self.area, "clone", "--quiet", str(self.repo), str(local))
      _run(local, "checkout", "-b", self.branch, self.source_sha)
      local_process = subprocess.run(
        [sys.executable, str(engine), "--root", str(local), "test", "RED"],
        cwd=local, capture_output=True, check=False,
      )
      wrapped_process = subprocess.run(
        [sys.executable, str(engine), "--root", str(self.repo),
         "test", "RED", "--remote", "0"],
        cwd=self.repo, capture_output=True, check=False,
      )
      self.assertEqual(
        (wrapped_process.returncode, wrapped_process.stdout,
         wrapped_process.stderr),
        (local_process.returncode, local_process.stdout, local_process.stderr),
      )

  def test_command_created_annotated_tag_is_published_and_read_back(self):
    tag = "v0.1.122-issue.786.2.25"
    def command(root, argv):
      _run(root, "tag", "-a", tag, self.source_sha, "-m", tag)
      return 0
    outcome = self.invoke(handler=command)
    self.assertEqual(outcome.exit_code, 0)
    ref = "refs/tags/" + tag
    self.assertEqual(
      _run(self.repo, "ls-remote", "origin", ref).split()[1], ref,
    )
    self.assertEqual(
      _run(self.repo, "ls-remote", "origin", ref + "^{}").split()[0],
      self.source_sha,
    )
    self.assertEqual(
      _run(self.repo, "ls-remote", "origin", "refs/heads/" + self.branch).split()[0],
      self.source_sha,
    )

  def test_command_cannot_replace_existing_authoritative_tag(self):
    tag = "v0.1.122-issue.786.2.25"
    _run(self.repo, "tag", "-a", tag, self.source_sha, "-m", tag)
    _run(self.repo, "push", "origin", "refs/tags/" + tag)
    original = _run(self.repo, "rev-parse", "refs/tags/" + tag)
    def command(root, argv):
      _run(root, "tag", "-f", "-a", tag, self.source_sha, "-m", "replacement")
      return 0
    outcome = self.invoke(handler=command)
    self.assertEqual(outcome.exit_code, 1)
    self.assertIn("rewrote an existing Git tag", outcome.stderr)
    self.assertEqual(
      _run(self.repo, "ls-remote", "origin", "refs/tags/" + tag).split()[0],
      original,
    )

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

  def test_forged_cmd_source_trailer_is_denied(self):
    self.marker("test RED --remote 1", source_identity="f" * 40)
    self.push()
    with self.assertRaisesRegex(RemoteInvocationError, "source identity"):
      self.invoke("test", "RED", "--remote", "1")

  def test_missing_cmd_source_trailer_is_denied(self):
    self.marker("test RED --remote 1")
    self.push()
    # Change only the request's commit message, preserving its request bytes.
    _run(self.repo, "commit", "--amend", "-m", "missing trailer")
    _run(self.repo, "push", "--force-with-lease", "origin", self.cmd)
    with self.assertRaisesRegex(RemoteInvocationError, "source identity"):
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

  def test_generic_non_test_command_can_run_read_only(self):
    self.alternate_request("issue info --remote 0")
    seen = []
    def command(root, args):
      seen.append(list(args))
      print("issue detail: λ")
      return 0
    outcome = self.invoke("issue", "info", "--remote", "0", handler=command)
    self.assertEqual(seen, [["issue", "info"]])
    self.assertEqual(outcome.exit_code, 0)
    self.assertEqual(outcome.stdout, "issue detail: λ\n")
    self.assertEqual(_run(self.area, "--git-dir", str(self.remote),
                          "rev-parse", self.branch), self.source_sha)

  def test_hosted_command_pushes_its_own_commit_even_on_nonzero(self):
    self.alternate_request("issue info --remote 0")
    def command(root, args):
      path = root / "owned.txt"
      path.write_text("durable\n", encoding="utf-8")
      from repo_workflow.owned_commit import commit_owned_files
      commit_owned_files(root, ["owned.txt"], "issue: commit owned state")
      print("command returned nine")
      return 9
    outcome = self.invoke("issue", "info", "--remote", "0", handler=command)
    self.assertEqual(outcome.exit_code, 9)
    self.assertEqual(outcome.stdout, "command returned nine\n")
    tip = _run(self.area, "--git-dir", str(self.remote), "rev-parse", self.branch)
    self.assertNotEqual(tip, self.source_sha)
    self.assertEqual(
      _run(self.area, "--git-dir", str(self.remote), "show", self.branch + ":owned.txt"),
      "durable",
    )

  def test_hosted_command_publishes_new_command_created_branch(self):
    self.alternate_request("issue info --remote 0")
    def command(root, args):
      _run(root, "checkout", "-b", "issue-787", self.source_sha)
      (root / "issue.txt").write_text("durable issue state\n", encoding="utf-8")
      from repo_workflow.owned_commit import commit_owned_files
      commit_owned_files(root, ["issue.txt"], "issue: own durable state")
      return 0
    outcome = self.invoke("issue", "info", "--remote", "0", handler=command)
    self.assertEqual(outcome.exit_code, 0, outcome.stderr)
    tip = _run(self.area, "--git-dir", str(self.remote), "rev-parse", "issue-787")
    self.assertEqual(_run(self.area, "--git-dir", str(self.remote),
                          "rev-parse", tip + "^"), self.source_sha)
    self.assertEqual(_run(self.area, "--git-dir", str(self.remote),
                          "show", "issue-787:issue.txt"), "durable issue state")
    self.assertEqual(_run(self.area, "--git-dir", str(self.remote),
                          "rev-parse", self.branch), self.source_sha)

  def test_hosted_command_rejects_uncommitted_mutations(self):
    self.alternate_request("issue info --remote 0")
    def command(root, args):
      (root / "forgotten.txt").write_text("not committed\n")
      return 0
    outcome = self.invoke("issue", "info", "--remote", "0", handler=command)
    self.assertEqual(outcome.exit_code, 1)
    self.assertIn("uncommitted repository changes", outcome.stderr)
    self.assertEqual(_run(self.area, "--git-dir", str(self.remote),
                          "rev-parse", self.branch), self.source_sha)

  def test_unsupported_hosted_grammar_rejected(self):
    self.alternate_request("version invalid --remote 0")
    outcome = self.invoke("version", "invalid", "--remote", "0")
    self.assertEqual(outcome.exit_code, 2)
    self.assertIn("not eligible", outcome.stderr)

  def test_read_only_results_rejected(self):
    self.alternate_request("test results --remote 0")
    outcome = self.invoke("test", "results", "--remote", "0")
    self.assertEqual(outcome.exit_code, 2)
    self.assertIn("read-only", outcome.stderr)

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

  def test_hosted_cmd_missing_suffix_rejected_before_handler(self):
    import importlib.util
    script = Path(__file__).resolve().parents[1] / "repo_workflow.py"
    spec = importlib.util.spec_from_file_location("rwf_786_missing", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    with redirect_stderr(output):
      status = module.main(["--root", str(self.repo), "test", "RED"])
    self.assertEqual(status, 2)
    self.assertIn("requires numbered --remote suffix", output.getvalue())
    self.assertFalse((self.repo / ".repoworkflow" / "validation").exists())

  def test_real_process_capture_preserves_bytes_and_status(self):
    outcome = self.invoke(handler=lambda root, args: subprocess.CompletedProcess(
      args=["rwf", *args],
      returncode=42,
      stdout="π output\n".encode("utf-8"),
      stderr="δ failure\n".encode("utf-8"),
    ))
    self.assertEqual(outcome.exit_code, 42)
    self.assertEqual(outcome.stdout, "π output\n")
    self.assertEqual(outcome.stderr, "δ failure\n")
    self.assertEqual(outcome.output, "π output\nδ failure\n")

  def test_utf8_emission_ignores_host_text_codec(self):
    out, err = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(out, encoding="cp1252")
    stderr = io.TextIOWrapper(err, encoding="cp1252")
    result = InvocationOutcome(
      self.cmd, "a" * 40, self.source_sha, 0, 7,
      "π", "δ", "πδ",
    )
    with patch("repo_workflow.remote_invocation.sys.stdout", stdout):
      with patch("repo_workflow.remote_invocation.sys.stderr", stderr):
        emit_outcome(result)
    self.assertEqual(out.getvalue(), "π".encode("utf-8"))
    self.assertEqual(err.getvalue(), "δ".encode("utf-8"))

  def test_invalid_subprocess_utf8_fails_closed(self):
    def invalid(root, args):
      return subprocess.CompletedProcess(
        args=["rwf", *args], returncode=0,
        stdout=bytes([255]), stderr=b"",
      )
    with self.assertRaisesRegex(RemoteInvocationError, "non-UTF-8"):
      self.invoke(handler=invalid)

if __name__ == "__main__":
  unittest.main()
