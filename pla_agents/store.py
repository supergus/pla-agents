"""Durable run store (SQLite, WAL). The PLA checkpoints after every step: run state (JSON) and the
program graph (Turtle) are written in one transaction, so a crash leaves the last complete step."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from rdflib import Graph

from .ontology import bind

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  graph TEXT NOT NULL,
  version INTEGER NOT NULL,
  updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
  run_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  label TEXT NOT NULL,
  at REAL NOT NULL,
  PRIMARY KEY (run_id, version)
);
"""


class RunStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)

    def save(self, run_id: str, state: dict, graph: Graph, label: str) -> int:
        ttl = graph.serialize(format="turtle")
        with self.db:  # one atomic transaction
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT version FROM runs WHERE run_id=?", (run_id,)).fetchone()
            version = (row[0] if row else 0) + 1
            state["version"] = version
            self.db.execute(
                "INSERT INTO runs(run_id,state,graph,version,updated) VALUES(?,?,?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET state=excluded.state, graph=excluded.graph, "
                "version=excluded.version, updated=excluded.updated",
                (run_id, json.dumps(state, sort_keys=True), ttl, version, time.time()))
            self.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (run_id, version, label, time.time()))
        return version

    def load(self, run_id: str) -> tuple[dict, Graph]:
        row = self.db.execute("SELECT state, graph FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"no run {run_id} in {self.path}")
        g = bind(Graph())
        g.parse(data=row[1], format="turtle")
        return json.loads(row[0]), g

    def exists(self, run_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is not None

    def list_runs(self) -> list[tuple[str, str, str]]:
        out = []
        for rid, st in self.db.execute("SELECT run_id, state FROM runs ORDER BY updated"):
            s = json.loads(st)
            out.append((rid, s.get("status"), s.get("stage")))
        return out

    def checkpoints(self, run_id: str) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT label FROM checkpoints WHERE run_id=? ORDER BY version", (run_id,))]

    def close(self):
        self.db.close()
