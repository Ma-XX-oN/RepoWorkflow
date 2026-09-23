from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SourceSizeTests(unittest.TestCase):
  def test_authoritative_implementation_files_stay_below_500_lines(self):
    files = [ROOT / "repo_workflow.py"]
    files.extend(sorted((ROOT / "repo_workflow").glob("*.py")))
    files.extend(sorted((ROOT / "helpers").glob("*.py")))
    files.append(ROOT / "templates" / "github" / "ci.yml")
    oversized = []
    for path in files:
      lines = len(path.read_text(encoding="utf-8").splitlines())
      if lines >= 500:
        oversized.append(f"{path.relative_to(ROOT)}={lines}")
    self.assertEqual(oversized, [], "oversized authoritative files: " + ", ".join(oversized))


if __name__ == "__main__":
  unittest.main()
