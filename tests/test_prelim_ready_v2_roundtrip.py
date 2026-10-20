"""Real bare-Git round trip: prepared candidate -> PASS identity -> READY."""
from unittest.mock import patch
import unittest

from repo_workflow.git import git
from repo_workflow.prelim_ready import ReadyPublicationError
from repo_workflow.prelim_ready_v2_prepare import prepare_destination_prelim
from repo_workflow.prelim_ready_v2_publish import publish_destination_prelim
from repo_workflow.prelim_ready_v2_validation import (
  validate_destination_prelim, v2_identity_key, v2_identity_ref,
)
from repo_workflow.state_store import durable_store
from tests.test_prelim_attempt import PrelimAttemptTests


G = "11111111-1111-4111-8111-111111111111"


class MissingRef(Exception):
  code = "not_found"


class GitProvider:
  repository = "Org/Repo"

  def __init__(self, bare):
    self.bare = bare
    self.writes = []

  def get(self, route):
    if route.startswith("git/commits/"):
      sha = route.removeprefix("git/commits/")
      if git(self.bare, "cat-file", "-e", sha + "^{commit}",
             check=False).returncode:
        raise MissingRef()
      return {"sha": sha}
    assert route.startswith("git/ref/")
    ref = "refs/" + route[len("git/ref/"):]
    observed = git(self.bare, "rev-parse", "--verify", ref, check=False)
    if observed.returncode:
      raise MissingRef()
    return {"ref": ref, "object": {"sha": observed.stdout.strip()}}

  def post(self, route, payload):
    assert route == "git/refs"
    git(self.bare, "update-ref", payload["ref"], payload["sha"],
        "0"*40)
    self.writes.append(dict(payload))
    return {"ref": payload["ref"]}


class DestinationRoundTripTests(unittest.TestCase):
  setUp = PrelimAttemptTests.setUp

  def test_prepared_source_remains_immutable_through_real_git_publication(self):
    candidate = prepare_destination_prelim(
      self.root, "7", "refs/heads/issue-7", "main", self.config,
      resolve_parent=lambda _: "main", guid=G,
    )
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/PRELIM-*").stdout.strip(), "")

    # The independent hosted terminal publisher makes the exact tested
    # object reachable through its immutable evidence tags, not READY refs.
    for tag in ("v1.2.4-issue.7.0.1", "v1.2.4-PRELIM-7.0.1"):
      git(self.root, "tag", tag, candidate.candidate_sha)
      git(self.root, "push", "origin", "refs/tags/" + tag)

    def observation(stage, sha, obj):
      self.assertEqual(sha, candidate.candidate_sha)
      return {
        "outcome": "PASS", "version": "1.2.4-issue.7.0.1",
        "tag": {"regression": "v1.2.4-issue.7.0.1",
                "integration": "v1.2.4-PRELIM-7.0.1"}[stage],
      }

    with (
      patch("repo_workflow.prelim_ready_v2_validation._observation",
            side_effect=observation),
      patch("repo_workflow.prelim_ready_v2_validation._remote_target",
            return_value=candidate.candidate_sha),
    ):
      accepted = validate_destination_prelim(
        self.root, G, self.config, regression=object(),
        integration=object(),
      )
    self.assertEqual(accepted["value"]["outcome"], "PASS")
    self.assertTrue(git(self.root, "ls-remote", "origin",
                        v2_identity_ref(G)).stdout.strip())
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/PRELIM-*").stdout.strip(), "")

    # A historical offline candidate may first become READY after destination
    # advancement. Its accepted SHA and tags remain historical; no rebase.
    git(self.root, "checkout", "main")
    (self.root / "later.txt").write_text("new remote parent\\n")
    git(self.root, "add", "--", "later.txt")
    git(self.root, "commit", "-m", "advance destination after PASS")
    git(self.root, "push", "origin", "main")
    git(self.root, "checkout", "issue-7")
    self.assertNotEqual(
      git(self.root, "ls-remote", "origin", "refs/heads/main")
      .stdout.split()[0], candidate.base_sha)

    # Restart recovery reads independent published state, not a local READY flag.
    local = durable_store(self.root)._path(v2_identity_key(G))
    local.unlink()
    provider = GitProvider(self.remote)
    with (
      patch("repo_workflow.prelim_ready_v2_publish.verify_ready_provider_scope"),
      patch("repo_workflow.prelim_ready_v2_publish._remote_target",
            return_value=candidate.candidate_sha),
    ):
      result = publish_destination_prelim(
        self.root, self.config, ticket=7, destination="main",
        guid=G, request_id="publish-7", backend=provider,
        resolve_parent=lambda _: "main",
      )
      self.assertEqual(result.sha, candidate.candidate_sha)
      self.assertEqual(len(provider.writes), 1)
      replay = publish_destination_prelim(
        self.root, self.config, ticket=7, destination="main",
        guid=G, request_id="publish-7", backend=provider,
        resolve_parent=lambda _: "main",
        read_publication_record=lambda request_id: {
          "ref": result.ref, "sha": result.sha,
          "request_id": request_id, "status": "published",
        },
      )
      self.assertEqual(replay, result)
      self.assertEqual(len(provider.writes), 1)
      with self.assertRaises(ReadyPublicationError):
        publish_destination_prelim(
          self.root, self.config, ticket=7, destination="main",
          guid=G, request_id="different", backend=provider,
          resolve_parent=lambda _: "main",
        )
    self.assertEqual(
      git(self.root, "ls-remote", "origin", result.ref)
      .stdout.split()[0], candidate.candidate_sha)

    # A separate coordinator-owned integration candidate must be rebuilt
    # against the current parent; historic PRELIM PASS is not promoted.
    git(self.root, "fetch", "origin", "refs/heads/main")
    advanced = git(self.root, "rev-parse", "FETCH_HEAD").stdout.strip()
    git(self.root, "checkout", "-b", "INT-ATTEMPT-issue-7/main-" + G,
        advanced)
    git(self.root, "merge", "--no-ff", "--no-edit", candidate.candidate_sha)
    reconstructed = git(self.root, "rev-parse", "HEAD").stdout.strip()
    self.assertNotEqual(reconstructed, candidate.candidate_sha)
    for ancestor in (advanced, candidate.candidate_sha):
      self.assertEqual(
        git(self.root, "merge-base", "--is-ancestor", ancestor,
            reconstructed, check=False).returncode, 0)
    self.assertEqual(
      durable_store(self.root).read(v2_identity_key(G))
      ["value"]["candidate_sha"], candidate.candidate_sha)
    self.assertEqual(
      git(self.root, "ls-remote", "origin", result.ref)
      .stdout.split()[0], candidate.candidate_sha)
    self.assertEqual(
      git(self.root, "ls-remote", "origin",
          "refs/heads/INT-ATTEMPT-*").stdout.strip(), "")


if __name__ == "__main__":
  unittest.main()
