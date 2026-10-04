"""Copy a fixed allowlist of attributed research fixtures; never touch evaluator data."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT.parent
FILES = {
    "data/focus/focus_sample.csv": "fixtures/billing/focus_sample.csv",
    "focus-license.md": "docs/licenses/FOCUS-license.md",
    "small_model_pack/knowledge_cards.json": "backend/proofops/models/development/knowledge_cards.json",
    "small_model_pack/few_shots.jsonl": "backend/proofops/models/development/few_shots.jsonl",
    "small_model_pack/answer_schema.json": "backend/proofops/models/development/answer_schema.json",
}

for source, target in FILES.items():
    destination = ROOT / target
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RESEARCH / source, destination)
print(f"Copied {len(FILES)} fixed, attributed development/billing fixtures; evaluator files excluded.")
