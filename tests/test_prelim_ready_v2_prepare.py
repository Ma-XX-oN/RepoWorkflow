"""Prove new PRELIM candidates are local until independent acceptance."""
import unittest

from repo_workflow.git import git
from repo_workflow.prelim_attempt_lock import PrelimError
from repo_workflow.prelim_ready_v2_prepare import prepare_destination_prelim
from repo_workflow.prelim_ready_v2_record import preparation_ref
from tests.test_prelim_attempt import PrelimAttemptTests


G = "11111111-1111-4111-8111-111111111111"
H = "22222222-2222-4222-8222-222222222222"


class DestinationPreparationTests(unittest.TestCase):
  setUp = PrelimAttemptTests.setUp

  def make(self, guid=G, destination="main"):
    return prepare_destination_prelim(
      self.root, "7", "refs/heads/issue-7", destination, self.config,
      resolve_parent=lambda _: destination, guid=guid)

  def test_local_first_use_is_not_ready(self):
    result = self.make()
    self.assertEqual(result.proposed_version, "1.2.4")
    self.assertEqual(result.source_sha, self.source)
    self.assertEqual(
      git(self.root, "rev-parse", preparation_ref(G)).stdout.strip(),
      result.candidate_sha)
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/PRELIM-*").stdout.strip(), "")
    self.assertEqual(self.make(), result)

  def test_nonmain_historical_parent(self):
    git(self.root, "branch", "issue-10", "main")
    git(self.root, "push", "origin", "issue-10")
    result = self.make(destination="issue-10")
    self.assertEqual(result.destination, "issue-10")
    self.assertEqual(result.base_sha,
                     git(self.root, "rev-parse", "main").stdout.strip())

  def test_offline_parent_advances_without_rewriting_preparation(self):
    result = self.make()
    git(self.root, "checkout", "main")
    (self.root / "later.txt").write_text("new parent\n")
    git(self.root, "add", "--", "later.txt")
    git(self.root, "commit", "-m", "parent advances")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-7")
    self.assertEqual(self.make(), result)

  def test_two_guids_do_not_publish_ready(self):
    self.assertNotEqual(self.make().candidate_sha,
                        self.make(H).candidate_sha)
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/PRELIM-*").stdout.strip(), "")

  def test_wrong_parent_rejected(self):
    with self.assertRaises(PrelimError):
      prepare_destination_prelim(
        self.root, "7", "refs/heads/issue-7", "main", self.config,
        resolve_parent=lambda _: "issue-10", guid=G)


if __name__ == "__main__":
  unittest.main()
