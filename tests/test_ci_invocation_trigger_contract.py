"""Prevent #109 native CI workflows from becoming ordinary push-triggered jobs."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def push_paths(source):
  lines = source.splitlines()
  push = next((
    n for n, line in enumerate(lines)
    if line == "  push:"
  ), None)
  if push is None:
    return None
  tail = []
  for line in lines[push + 1:]:
    if line and not line.startswith("    ") and not line.startswith("#"):
      break
    tail.append(line)
  for n, line in enumerate(tail):
    if line.startswith("    paths:"):
      inline = line.partition(":")[2].strip()
      if inline:
        if not (inline.startswith("[") and inline.endswith("]")):
          return ["INVALID_INLINE_PATH_FILTER"]
        return [p.strip().strip("'\"") for p in inline[1:-1].split(",")]
      values = []
      for entry in tail[n + 1:]:
        if not entry.startswith("      "):
          break
        text = entry.strip()
        if not text or text.startswith("#"):
          continue
        if not text.startswith("- "):
          return ["INVALID_PATH_ENTRY"]
        values.append(text[2:].strip("'\""))
      return values
  return []


class ExplicitCiInvocationTests(unittest.TestCase):
  def test_on_demand_and_109_push_workflows_use_only_run_marker(self):
    paths = [WORKFLOWS / "on-demand-ci.yml"]
    paths.extend(sorted(WORKFLOWS.glob("issue-109-*.yml")))
    self.assertGreaterEqual(len(paths), 1)
    for path in paths:
      with self.subTest(workflow=path.name):
        self.assertTrue(path.is_file())
        requested = push_paths(path.read_text(encoding="utf-8"))
        if requested is not None:
          self.assertEqual(requested, [".ci/run"])


if __name__ == "__main__":
  unittest.main()
