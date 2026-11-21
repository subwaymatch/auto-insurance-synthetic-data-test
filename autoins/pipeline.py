"""Run the whole generator for one configuration."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import claims, config as C, identifiers, ledger, population, quotes, refdata, simulate, tables

# What the content hashes cover, recorded in run_summary.json so a copy of the output can be checked on its own
HASH_METHOD = ("sha256 over the CSV files in sorted order of their paths relative to the output folder (forward "
               "slashes), each path's UTF-8 bytes followed by the file's bytes; the first 16 hex digits")
GENERATOR_FILES = ["autoins", "reference", "generate.py", "requirements.txt"]


def generate(cfg: C.Config) -> dict:
    """Generate the dataset into cfg.out_dir. Returns the run summary written to run_summary.json: the run's
    settings and row counts, hashes of the CSVs written, and what built them (see build_manifest)."""
    ref = refdata.load(cfg)
    pop = population.build(cfg, ref)
    res = simulate.run(cfg, ref, pop)
    dev = claims.develop(cfg, ref, res)
    T, K = tables.build(cfg, ref, pop, res, dev)
    T["quote"] = quotes.build(cfg, ref, pop, res)
    identifiers.finish(cfg, ref.cal, T, K)       # business keys; surrogate keys renumbered in creation order
    T.update(ledger.build(cfg, ref.cal, T))      # the general ledger and commission statements, from those tables
    summary = {"seed": cfg.seed, "policies": cfg.n_policies, "start": cfg.start, "valuation": cfg.valuation,
               "rows": {k: len(v) for k, v in T.items()}, "answer_key_rows": {k: len(v) for k, v in K.items()}}
    tables.write(T, K, res.plan, cfg)
    out = Path(cfg.out_dir)
    summary["content_hash"] = content_hash(out)
    summary["tables_hash"] = content_hash(out, "*.csv")
    summary["answer_key_hash"] = content_hash(out / "answer_key")
    summary["hash_method"] = HASH_METHOD
    summary["build"] = build_manifest(T, K)
    (out / "run_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def content_hash(out_dir, pattern: str = "**/*.csv") -> str:
    """Hash of the CSVs under out_dir matching pattern ("**/*.csv": every one, answer key included; "*.csv": the
    data tables only). See HASH_METHOD."""
    out_dir = Path(out_dir)
    digest = hashlib.sha256()
    for f in sorted(out_dir.glob(pattern)):
        digest.update(f.relative_to(out_dir).as_posix().encode() + f.read_bytes())
    return digest.hexdigest()[:16]


def build_manifest(T: dict, K: dict) -> dict:
    """What produced the files: the generator's source revision (and whether its files had uncommitted changes),
    the library versions (which can change the random draws and number formatting), fingerprints of the reference
    data read and of the tables' columns. Nothing here depends on when or where the run happened, so the same
    source, libraries and seed give the same run_summary.json."""
    repo = C.REPO
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, timeout=30)
    try:
        rev = git("rev-parse", "HEAD")
        revision = rev.stdout.strip() if rev.returncode == 0 else None
        dirty = bool(git("status", "--porcelain", "--untracked-files=no", "--", *GENERATOR_FILES).stdout.strip()) if revision else None
    except (OSError, subprocess.SubprocessError):
        revision = dirty = None
    sha = lambda b: hashlib.sha256(b).hexdigest()[:16]
    columns = [f"{name}:{','.join(df.columns)}" for name, df in sorted({**T, **{f"answer_key/{k}": v for k, v in K.items()}}.items())]
    return {"source_revision": revision, "source_modified": dirty,
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "schema_fingerprint": sha("\n".join(columns).encode()),
            "reference_data": {f.name: sha(f.read_bytes()) for f in sorted(C.REFERENCE_DIR.glob("*.csv"))}}
