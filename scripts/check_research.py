"""Read-only checksum audit of the research pack; stores its manifest in the app."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT.parent
MANIFEST = ROOT / "docs/research_checksums.json"


def hashes():
    records = {}
    for parent, directories, files in os.walk(RESEARCH):
        directories[:] = [name for name in directories if name not in {"proofops-app", ".git", ".agents", ".codex", ".aws"}]
        for name in files:
            path = Path(parent) / name
            if path.is_symlink():
                continue
            records[str(path.relative_to(RESEARCH))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return records


parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true")
args = parser.parse_args()
current = hashes()
if args.record:
    if MANIFEST.exists():
        raise SystemExit("Initial research manifest already exists; refusing to replace it.")
    MANIFEST.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(current)} read-only research checksums.")
else:
    expected = json.loads(MANIFEST.read_text())
    changed = [name for name, checksum in expected.items() if current.get(name) != checksum]
    print(json.dumps({"checked": len(expected), "changed_or_missing": changed, "new_research_files": sorted(set(current) - set(expected))}))
    raise SystemExit(bool(changed))
