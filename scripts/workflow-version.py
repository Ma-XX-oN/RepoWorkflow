#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
print((ROOT / "VERSION").read_text(encoding="utf-8").strip())
