"""Independent concurrent publishers must not both create a success."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from repo_workflow.github_exact_check import (
  CONTEXT, PublishError, VerifiedDecision, publish,
)

SHA = "a" * 40
BASE = "b" * 40
REF = "refs/heads/rwf-exact-check-lock/" + SHA


class SharedRemote:
  def __init__(self):
    self.barrier = threading.Barrier(2)
    self.mutex = threading.Lock()
    self.lock_created = False
    self.statuses = []

  def __call__(self, path, payload=None):
    if path == "/branches/main":
      return {"commit": {"sha": BASE}}
    if path == "/commits/" + SHA + "/statuses":
      with self.mutex:
        return list(reversed(self.statuses))
    if path == "/git/refs":
      self.barrier.wait(timeout=5)
      with self.mutex:
        if self.lock_created:
          raise PublishError("remote ref already exists")
        self.lock_created = True
      return {"ref": REF, "object": {"sha": SHA}}
    if path == "/git/ref/heads/rwf-exact-check-lock/" + SHA:
      return {"ref": REF, "object": {"sha": SHA}}
    if path == "/statuses/" + SHA:
      with self.mutex:
        value = {"id": len(self.statuses) + 1,
                 "context": CONTEXT, "state": payload["state"],
                 "creator": {"login": "runner"},
                 "description": payload["description"]}
        self.statuses.append(value)
        return value
    raise AssertionError(path)


def decision(_, sha, base):
  return VerifiedDecision(sha, base, "trusted-job", "runner", True)


class ConcurrencyTests(unittest.TestCase):
  def test_two_independent_writers_one_success(self):
    remote = SharedRemote()

    def worker(_):
      try:
        return publish("user/disposable", SHA, BASE, "main", "token",
                       evidence={}, verifier=decision, provider=remote)
      except PublishError:
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
      results = list(pool.map(worker, range(2)))

    self.assertEqual(sum(result is not None for result in results), 1)
    self.assertEqual(len(remote.statuses), 1)
    self.assertEqual(remote.statuses[0]["state"], "success")
    self.assertTrue(remote.lock_created)


if __name__ == "__main__":
  unittest.main()
