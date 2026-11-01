"""Candidates from a YAML file.

Keep recovery candidates in configuration instead of code. The file is read when the registry is
empty, so reopening a database never duplicates or overwrites candidates.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/01_candidates/02_candidates_from_yaml.py
"""

import tempfile
from pathlib import Path

from arclayer import ArcLayer

CANDIDATES_FILE = Path(__file__).with_name("candidates.yaml")

layer = ArcLayer(None, candidates=CANDIDATES_FILE)
for spec in layer.candidates():
    print(f"loaded {spec.candidate_id}: needs host capability {spec.required_host_capabilities}")

with tempfile.TemporaryDirectory() as folder:
    database = f"sqlite:///{folder}/arclayer.db"
    first = ArcLayer(database, candidates=CANDIDATES_FILE)
    print("candidates after the first start:", len(first.candidates()))
    second = ArcLayer(database, candidates=CANDIDATES_FILE)  # the same database, opened again
    print("candidates after reopening the database:", len(second.candidates()))
