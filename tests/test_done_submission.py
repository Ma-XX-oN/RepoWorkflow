"""Real local Git completion submission; repository-info is an isolated fixture."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from repo_workflow.done_cli import DoneCommandError
from repo_workflow.done_submission import prepare_submission_candidate
from repo_workflow.git import git
from repo_workflow.parent_branch import create_parent_identity
from repo_workflow.public_cli import handle_public


class DoneSubmissionTests(unittest.TestCase):
  """Exercise normal command dispatch without an injected done executor."""

  def setUp(self):
    """Create an issue, permanent parent identity and separate bare provider."""
    directory = tempfile.TemporaryDirectory()
    self.addCleanup(directory.cleanup)
    base = Path(directory.name)
    self.root, self.remote = base / "work", base / "provider.git"
    self.root.mkdir()
    self.remote.mkdir()
    git(self.remote, "init", "--bare")
    git(self.root, "init", "-b", "main")
    git(self.root, "config", "user.name", "Fixture")
    git(self.root, "config", "user.email", "fixture@example.invalid")
    (self.root / "VERSION").write_text("0.1.0\n", encoding="utf-8", newline="\n")
    (self.root / "file").write_text("base\n", encoding="utf-8")
    (self.root / ".gitignore").write_text(
      ".repoworkflow/state/\n.repoworkflow/manual/\n", encoding="utf-8")
    (self.root / "scripts").mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts/merge-ticket-state.py",
                    self.root / "scripts/merge-ticket-state.py")
    self.commit("base")
    git(self.root, "remote", "add", "origin", str(self.remote))
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "-b", "issue-51-work")
    create_parent_identity(self.root, "issue-51-work", "main")
    (self.root / "feature").write_text("issue work\n", encoding="utf-8")
    self.source = self.commit("feature")
    for name, value in (
        ("repository_info", {"schema_version":1,"repository":"Org/Repo","provider":"fixture"}),
        ("resolve_info_config", {})):
      mocked = patch("repo_workflow.done_submission." + name, return_value=value)
      mocked.start()
      self.addCleanup(mocked.stop)

  def commit(self, message):
    """Commit fixture inputs and return their exact source SHA."""
    git(self.root, "add", ".")
    git(self.root, "commit", "-m", message)
    return git(self.root, "rev-parse", "HEAD").stdout.strip()

  def invoke(self):
    """Invoke the normal public command and return its submission JSON."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      status = handle_public(self.root, ["done", "patch"], engine_root=self.root)
    self.assertEqual(status, 0, output.getvalue())
    return json.loads(output.getvalue())

  def refs(self):
    """Read physical provider refs without inferring any merge outcome."""
    raw = git(self.remote, "show-ref", check=False).stdout
    return {line.split()[1]:line.split()[0] for line in raw.splitlines()}

  def advance_parent(self, *, conflict=False):
    """Advance the actual provider parent independently from the issue."""
    git(self.root, "checkout", "main")
    path = self.root / ("file" if conflict else "parent-feature")
    path.write_text("parent change\n", encoding="utf-8")
    sha = self.commit("parent advance")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-51-work")
    return sha

  def test_default_public_done_publishes_version_without_claiming_merge(self):
    """Missing tests permit submission but do not create PASS or DONE."""
    parent = self.refs()["refs/heads/main"]
    result = self.invoke()
    self.assertEqual(result["result"], "submitted")
    self.assertEqual(result["prelim_ref"], "refs/heads/PRELIM-issue-51.1.0")
    self.assertEqual(self.refs()[result["prelim_ref"]], result["candidate_sha"])
    self.assertEqual(self.refs()["refs/heads/main"], parent)
    self.assertFalse(any(name.startswith("refs/tags/v") for name in self.refs()))

  def test_unchanged_resume_reuses_version_and_physical_objects(self):
    """Report-free unchanged completion does not manufacture a new submission."""
    first = self.invoke()
    before = self.refs()
    second = self.invoke()
    self.assertEqual(first, second)
    self.assertEqual(self.refs(), before)

  def test_source_change_after_deferred_submission_gets_a_new_version(self):
    """The published version remains fixed even before server tests execute."""
    first = self.invoke()
    (self.root / "feature").write_text("corrected issue work\n", encoding="utf-8")
    self.commit("source correction")
    second = self.invoke()
    self.assertEqual(second["prelim_ref"], "refs/heads/PRELIM-issue-51.2.0")
    self.assertEqual(self.refs()[first["prelim_ref"]], first["candidate_sha"])

  def test_stale_source_is_copied_to_parent_and_versioned_before_testing(self):
    """Reconstruction includes both exact source and current parent history."""
    self.invoke()
    source = git(self.root, "rev-parse", "HEAD").stdout.strip()
    parent = self.advance_parent()
    result = self.invoke()
    self.assertEqual(result["parent_sha"], parent)
    self.assertEqual(result["prelim_ref"], "refs/heads/PRELIM-issue-51.1.1")
    for ancestor in (source, parent):
      self.assertEqual(git(self.root, "merge-base", "--is-ancestor", ancestor,
                           result["candidate_sha"], check=False).returncode, 0)
    self.assertEqual(git(self.root, "rev-parse", "HEAD").stdout.strip(), source)
    self.assertEqual(self.refs()["refs/heads/main"], parent)

  def test_parent_reintegration_resumes_without_another_increment(self):
    """Rebuilding an unchanged implementation versions once per parent tip."""
    self.invoke()
    parent = self.advance_parent()
    first = self.invoke()
    self.assertEqual(first["version"], "0.1.0-issue.51.1.1")
    self.assertEqual(self.invoke(), first)
    git(self.root, "checkout", "main")
    (self.root / "next-parent").write_text("next\n", encoding="utf-8")
    self.commit("second parent advance")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-51-work")
    second = self.invoke()
    self.assertEqual(second["version"], "0.1.0-issue.51.1.2")
    self.assertNotEqual(second["parent_sha"], parent)

  def test_changed_implementation_and_parent_reset_reintegration_counter(self):
    """A new implementation starts at R=0 even when the parent also moved."""
    self.invoke()
    (self.root / "feature").write_text("new implementation\n", encoding="utf-8")
    self.commit("implementation revision")
    self.advance_parent()
    result = self.invoke()
    self.assertEqual(result["version"], "0.1.0-issue.51.2.0")
    self.assertEqual(self.invoke(), result)

  def test_first_submission_on_new_parent_keeps_first_implementation_on_resume(self):
    """Initial preparation and parent copying share Q=1/R=0."""
    self.advance_parent()
    first = self.invoke()
    self.assertEqual(first["version"], "0.1.0-issue.51.1.0")
    self.assertEqual(self.invoke(), first)

  def test_current_candidate_can_be_prepared_from_a_different_checkout(self):
    """Checkout location alone cannot change the pinned source or version."""
    first = self.invoke()
    (self.root / "feature").write_text("later checkout work\n", encoding="utf-8")
    self.commit("unrelated current checkout")
    candidate, version = prepare_submission_candidate(
      self.root, first["candidate_sha"], first["parent_sha"], None, 51, self.root)
    self.assertEqual(candidate, first["candidate_sha"])
    self.assertEqual(version, first["version"])

  def test_current_failure_stops_before_versioning_or_publication(self):
    """Deferral cannot hide an applicable failed test."""
    log = self.root / ".repoworkflow/validation/testResults-51.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"testSHA":self.source,"kind":"regression",
                               "runner":"fixture","result":"failed"}) + "\n", encoding="utf-8")
    before = self.refs()
    with self.assertRaisesRegex(DoneCommandError, "failed test"):
      self.invoke()
    self.assertEqual(self.refs(), before)
    self.assertFalse((self.root / ".ci/engine-version").exists())

  def test_conflict_preserves_parent_and_persists_handoff(self):
    """A failed copy neither publishes PRELIM nor changes the destination."""
    (self.root / "file").write_text("issue change\n", encoding="utf-8")
    self.commit("conflicting issue change")
    parent = self.advance_parent(conflict=True)
    with self.assertRaisesRegex(DoneCommandError, "durable handoff"):
      self.invoke()
    self.assertEqual(self.refs()["refs/heads/main"], parent)
    self.assertFalse(any(name.startswith("refs/heads/PRELIM-") for name in self.refs()))
    receipts = list((self.root / ".repoworkflow/state/issues/51/done-conflicts").glob("*.json"))
    self.assertEqual(len(receipts), 1)
