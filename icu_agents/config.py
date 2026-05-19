import os
from pathlib import Path

OPENAI_MODEL = "gpt-4o-mini"

MAX_ICU_HOURS = 72

SEED = 42

# "eicu" loads PhysioNet demo SQLite; "synthetic" uses random generators only.
DATA_SOURCE = os.environ.get("ICU_DATA_SOURCE", "eicu").lower()

REPO_ROOT = Path(__file__).resolve().parent.parent
EICU_DEMO_DIR = Path(os.environ.get("EICU_DEMO_DIR", REPO_ROOT / "data" / "eicu-crd-demo"))
