"""Real local Git comparison of fast-forward and expected-old CAS."""
from pathlib import Path
import subprocess
import tempfile
import unittest


def git(root, *args, check=True):
  result = subprocess.run(
    ["git", "-C", str(root), *args],
    text=True, capture_output=True, check=check,
  )
  return result


class DestinationCasGitTests(unittest.TestCase):
  def test_second_stale_actor_is_rejected_even_if_fast_forward(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      git(root, "init", "-b", "main")
      git(root, "config", "user.email", "local@example.invalid")
      git(root, "config", "user.name", "Local CAS Fixture")
      commits = []
      for value in ("A", "B", "C"):
        (root / "state.txt").write_text(value + "\n")
        git(root, "add", "state.txt")
        git(root, "commit", "-m", value)
        commits.append(git(root, "rev-parse", "HEAD").stdout.strip())
      a, b, c = commits
      git(root, "update-ref", "refs/heads/main", a, c)
      first = git(root, "update-ref", "refs/heads/main", b, a)
      self.assertEqual(first.returncode, 0)
      second = git(root, "update-ref", "refs/heads/main", c, a,
        check=False)
      self.assertNotEqual(second.returncode, 0)
      self.assertEqual(
        git(root, "rev-parse", "refs/heads/main").stdout.strip(), b)
      self.assertEqual(
        git(root, "merge-base", "--is-ancestor", b, c).returncode, 0)


if __name__ == "__main__":
  unittest.main()
