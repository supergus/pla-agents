"""Fetch the rfq-ontology dependency at the commit pinned in ontology.lock.

Usage: python scripts/fetch_ontology.py [--dest vendor/rfq-ontology]

Idempotent: if the destination already holds the pinned commit, nothing happens.
Set RFQ_ONTOLOGY_DIR to use a local checkout instead (the PLA then skips vendor/).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_lock(path: Path = ROOT / "ontology.lock") -> dict[str, str]:
    out = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            k, v = (s.strip() for s in line.split("=", 1))
            out[k] = v
    if not {"repo", "commit"} <= out.keys():
        raise SystemExit("ontology.lock needs `repo` and `commit`")
    return out


def git(*args, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fetch(dest: Path) -> str:
    lock = read_lock()
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        try:
            if git("rev-parse", "HEAD", cwd=dest) == lock["commit"]:
                return lock["commit"]
        except subprocess.CalledProcessError:
            pass
    else:
        git("init", "-q", cwd=dest)
        git("remote", "add", "origin", lock["repo"], cwd=dest)
    git("fetch", "-q", "--depth", "1", "origin", lock["commit"], cwd=dest)
    git("checkout", "-q", "--force", "FETCH_HEAD", cwd=dest)
    head = git("rev-parse", "HEAD", cwd=dest)
    if head != lock["commit"]:
        raise SystemExit(f"fetched {head}, expected {lock['commit']}")
    return head


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=str(ROOT / "vendor" / "rfq-ontology"))
    a = ap.parse_args()
    print(f"rfq-ontology @ {fetch(Path(a.dest))} -> {a.dest}", file=sys.stderr)
