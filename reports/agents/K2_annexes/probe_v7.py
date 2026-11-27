"""K2 — K1's 64-query retrieval probe (reports/agents/K1_annexes/retrieval_probe.py, imported
read-only) run on index/tas_v7 with the SAME queries (built from tas_v6, seed 7). Outputs go to
reports/agents/K2_annexes/probe_v7/ (K1's files are not touched)."""
import importlib.util, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
K1 = ROOT / "reports/agents/K1_annexes"
sys.path.insert(0, str(K1))
spec = importlib.util.spec_from_file_location("k1_probe", K1 / "retrieval_probe.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
qs = m.build_queries()
m.build_queries = lambda: qs
m.IDX = ROOT / "index" / sys.argv[1]
m.OUT = Path(__file__).resolve().parent / f"probe_{sys.argv[1]}"
m.OUT.mkdir(exist_ok=True)
m.main()
