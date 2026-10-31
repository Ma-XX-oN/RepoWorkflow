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
  def test_push_workflows_have_explicit_paths(self):
    exceptions = {
      "lane-cache-routing-certification.yml",
      "native-dependency-lane-certification-v1.yml",
      "native-dependency-migration-v1.yml",
    }
    paths = sorted(WORKFLOWS.glob("*.yml"))
    self.assertGreaterEqual(len(paths), 1)
    for path in paths:
      with self.subTest(workflow=path.name):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        self.assertEqual(lines.count("on:"), 1)
        self.assertFalse(any(
          line.startswith("  push") and line != "  push:"
          for line in lines
        ))
        requested = push_paths(source)
        if requested is None:
          continue
        if path.name in exceptions:
          self.assertTrue(requested)
        else:
          self.assertEqual(requested, [".ci/run"])


if __name__ == "__main__":
  unittest.main()
