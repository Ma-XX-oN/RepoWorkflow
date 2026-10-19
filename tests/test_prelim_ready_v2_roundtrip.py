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
    for tag in ("v1.2.4-REGRESSION-PASS", "v1.2.4-INTEGRATION-PASS"):
      git(self.root, "tag", tag, candidate.candidate_sha)
      git(self.root, "push", "origin", "refs/tags/" + tag)

    def observation(stage, sha, obj):
      self.assertEqual(sha, candidate.candidate_sha)
      return {"outcome": "PASS", "version": "1.2.4",
              "tag": "v1.2.4-" + stage.upper() + "-PASS"}

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
      with self.assertRaises(ReadyPublicationError):
        publish_destination_prelim(
          self.root, self.config, ticket=7, destination="main",
          guid=G, request_id="different", backend=provider,
          resolve_parent=lambda _: "main",
        )
    self.assertEqual(
      git(self.root, "ls-remote", "origin", result.ref)
      .stdout.split()[0], candidate.candidate_sha)


if __name__ == "__main__":
  unittest.main()
