import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
EVALS = Path(__file__).resolve().parents[2]
for path in (BACKEND, EVALS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
