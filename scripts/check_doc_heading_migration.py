"""Temporary exact-revision Markdown heading/link migration verifier."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

BASE = "39a33cf11a60a7fedd6d5d2a396a5d111b723bf1"
NEW = "HEAD"
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)\s*#*\s*$")
ORDER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]\n]+\]:\s*<?([^>\s]+)>?", re.M)
HTML_LINK = re.compile(r"href=[\"']([^\"']+)[\"']")
SELF_URL = "github.com/Ma-XX-oN/RepoWorkflow/blob/main/"
failures = []
warnings = []

def git(*args):
  return subprocess.check_output(["git", *args], text=True, encoding="utf-8")

def files(rev):
  return {
    p for p in git("ls-tree", "-r", "--name-only", rev).splitlines()
    if p.endswith(".md")
  }

def source(rev, path):
  return git("show", rev + ":" + path)

def active_lines(text):
  fenced = False
  char = ""
  count = 0
  for line in text.splitlines():
    fence = re.match(r"^\s*(\`{3,}|~{3,})", line)
    if fence:
      if not fenced:
        fenced = True
        char = fence.group(1)[0]
        count = len(fence.group(1))
      elif fence.group(1)[0] == char and len(fence.group(1)) >= count:
        fenced = False
      continue
    if not fenced:
      yield line

def slug(text):
  text = re.sub(r"<[^>]+>", "", text)
  return "".join(
    c for c in text.lower() if c.isalnum() or c in "-_ "
  ).replace(" ", "-")

def headings(text):
  result = {}
  titles = []
  used = Counter()
  for line in active_lines(text):
    match = HEADING.match(line)
    if not match:
      continue
    title = match.group(1).strip()
    base = slug(title)
    suffix = used[base]
    anchor = base + ("-" + str(suffix) if suffix else "")
    used[base] += 1
    result[anchor] = title
    titles.append(title)
  return result, titles

def links(text):
  out = []
  for line in active_lines(text):
    for m in MARKDOWN_LINK.finditer(line):
      out.append(m.group(1).strip().split(" ", 1)[0].strip("<>"))
    for m in REFERENCE_LINK.finditer(line):
      out.append(m.group(1))
    for m in HTML_LINK.finditer(line):
      out.append(m.group(1))
  return out

def destination(owner, link, known, heads):
  if link.startswith(("mailto:", "data:", "javascript:")):
    return None
  bits = urlsplit(link)
  if bits.scheme in ("http", "https"):
    if bits.netloc != "github.com" or SELF_URL not in link:
      return None
    path = link.split(SELF_URL, 1)[1].split("#", 1)[0].split("?", 1)[0]
    fragment = bits.fragment
  else:
    if bits.scheme or bits.netloc:
      return None
    path = str(PurePosixPath(owner).parent / unquote(bits.path)) if bits.path else owner
    path = str(PurePosixPath(path))
    fragment = bits.fragment
  path = re.sub(r"(^|/)\./", r"\1", path)
  while "/../" in path:
    path = re.sub(r"(^|/)[^/]+/\.\./", r"\1", path)
  if path not in known:
    if not path.endswith(".md"):
      return None  # non-Markdown links are outside the heading migration
    return ("INVALID_FILE", path)
  if not fragment:
    return ("FILE", path)
  value = heads[path].get(unquote(fragment))
  return ("HEADING", path, value) if value is not None else ("INVALID_ANCHOR", path, fragment)

base_files = files(BASE)
new_files = files(NEW)
if base_files != new_files:
  failures.append("Markdown file set changed unexpectedly")
original = {}
migrated = {}
for path in sorted(base_files | new_files):
  original[path] = source(BASE, path)
  migrated[path] = source(NEW, path)
oldheads = {p: headings(s)[0] for p, s in original.items()}
newheads = {p: headings(s)[0] for p, s in migrated.items()}
total_numbered = 0
link_count = 0
changed_links = 0
for path in sorted(base_files & new_files):
  a = headings(original[path])[1]
  b = headings(migrated[path])[1]
  if path.startswith(".repoworkflow/"):
    if original[path] != migrated[path]:
      failures.append(path + ": historical record changed")
    continue
  expected = [ORDER.sub("", title, count=1) for title in a]
  if expected != b:
    failures.append(path + ": heading order/text mismatch")
  total_numbered += sum(bool(ORDER.match(title)) for title in a)
  if any(ORDER.match(title) for title in b):
    failures.append(path + ": presentation numbering remains")
  oldlinks = links(original[path])
  newlinks = links(migrated[path])
  if len(oldlinks) != len(newlinks):
    failures.append(path + ": link count changed " + str((len(oldlinks), len(newlinks))))
    continue
  for before, after in zip(oldlinks, newlinks):
    link_count += 1
    old = destination(path, before, base_files, oldheads)
    new = destination(path, after, new_files, newheads)
    if before != after:
      changed_links += 1
    if new is not None and new[0].startswith("INVALID"):
      if old is not None and old[0].startswith("INVALID") and before == after:
        warnings.append(path + " pre-existing: " + after + " " + str(new))
      else:
        failures.append(path + " broken link: " + after + " " + str(new))
    if old is not None and new is not None and old[0] == "HEADING" and new[0] == "HEADING":
      original_title = ORDER.sub("", old[2], count=1)
      if original_title != new[2] or old[1] != new[1]:
        failures.append(path + " link moved to wrong section: " + before + " -> " + after)
    elif before != after and (old is None or new is None or old[0] != new[0]):
      failures.append(path + " changed link lacks equivalent target: " + before + " -> " + after)
print("Potential numbered prose-section references:")
for path in sorted(base_files & new_files):
  if path.startswith(".repoworkflow/"):
    continue
  for number, line in enumerate(active_lines(migrated[path]), 1):
    if re.search(r"(?i)(?:\\bsections?\\s+|§\\s*)\\d+(?:\\.\\d+)*\\b", line):
      print("REFERENCE", path, number, line.strip()[:220])
print("Markdown files:", len(base_files))
print("Numbered headings migrated:", total_numbered)
print("Links checked:", link_count, "modified:", changed_links)
print("Pre-existing invalid links:", len(warnings))
for warning in warnings[:30]:
  print("PRE-EXISTING:", warning)
print("Failures:", len(failures))
for failure in failures[:100]:
  print("FAIL:", failure)
if failures:
  sys.exit(1)
