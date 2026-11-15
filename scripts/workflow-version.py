#!/usr/bin/env python3
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
  print((ROOT / "VERSION").read_text(encoding="utf-8").strip())
  return 0


if __name__ == "__main__":
  sys.path.insert(0, str(ROOT))
  from repo_workflow.output import configure_utf8_output
  if not configure_utf8_output():
    raise SystemExit(2)
  raise SystemExit(main())
