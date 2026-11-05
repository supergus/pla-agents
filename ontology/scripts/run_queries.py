"""Run every SPARQL competency query in queries/ against data + computed results and print the rows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rfqlib import ROOT, all_data  # noqa: E402


def graph_with_results():
    g = all_data()
    res = ROOT / "build" / "quote-results.ttl"
    if res.exists():
        g.parse(res)
    return g


def short(v):
    s = str(v)
    return s.rsplit("#", 1)[-1] if s.startswith("http") else s


def run(name, g=None):
    g = g or graph_with_results()
    return [tuple(short(v) if v is not None else None for v in row) for row in g.query((ROOT / "queries" / name).read_text())]


if __name__ == "__main__":
    g = graph_with_results()
    for q in sorted((ROOT / "queries").glob("*.rq")):
        print(f"== {q.name}: {q.read_text().splitlines()[0][2:]}")
        for row in run(q.name, g):
            print("   ", " | ".join("" if v is None else v for v in row))
