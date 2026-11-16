from pathlib import Path
import unittest


# Why this structural gate also exists for single-read agent retrieval:
# SOURCE_SIZE_RATIONALE.md (linked from DOCUMENTATION_STRUCTURE.md).
ROOT = Path(__file__).resolve().parents[1]


class SourceSizeTests(unittest.TestCase):
  def test_authoritative_files_stay_below_800_lines(self):
    files = [ROOT / "repo_workflow.py"]
    files.extend(sorted((ROOT / "repo_workflow").glob("*.py")))
    files.extend(sorted((ROOT / "helpers").glob("*.py")))
    files.append(ROOT / "templates" / "github" / "ci.yml")
    files.extend(sorted(ROOT.glob("*.md")))
    oversized = []
    for path in files:
      lines = len(path.read_text(encoding="utf-8").splitlines())
      if lines >= 800:
        oversized.append(f"{path.relative_to(ROOT)}={lines}")
    self.assertEqual(oversized, [], "oversized authoritative files: " + ", ".join(oversized))


if __name__ == "__main__":
  unittest.main()
