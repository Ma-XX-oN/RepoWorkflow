"""Associate existing catalogue groups with an issue in that same catalogue."""
from pathlib import Path
import json

from .current_work_store import CurrentWorkStore
from .owned_commit import commit_owned_files
from .test_catalogue import CATALOGUE_PATH, load_test_catalogue


class HighRiskError(RuntimeError):
  pass


def associate_high_risk(root: Path, aliases, writer):
  root = Path(root).resolve()
  requested = tuple(aliases)
  if not requested:
    raise HighRiskError("at least one catalogue alias is required")
  catalogue = load_test_catalogue(root)
  groups = catalogue.expand_aliases(requested)
  reference = CurrentWorkStore(root).read().value.current
  if reference is None:
    raise HighRiskError("rwf high-risk requires an active current issue")
  key = "issue-" + reference.issue
  selected = sorted(set(catalogue.aliases.get(key, ())) | set(groups))
  path = root / CATALOGUE_PATH
  value = json.loads(path.read_text(encoding="utf-8"))
  if value.setdefault("aliases", {}).get(key) != selected:
    value["aliases"][key] = selected
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    commit_owned_files(root, [CATALOGUE_PATH.as_posix()],
                       f"test: select additional groups for issue {reference.issue}")
  return {"issue": reference.issue, "groups": selected}
