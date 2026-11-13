"""Run the whole generator for one configuration."""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import claims, config as C, population, refdata, simulate, tables


def generate(cfg: C.Config) -> dict:
    """Generate the dataset into cfg.out_dir. Returns a summary including a hash of every CSV written."""
    ref = refdata.load(cfg)
    pop = population.build(cfg, ref)
    res = simulate.run(cfg, ref, pop)
    dev = claims.develop(cfg, ref, res)
    T, K = tables.build(cfg, ref, pop, res, dev)
    summary = {"seed": cfg.seed, "policies": cfg.n_policies, "start": cfg.start, "valuation": cfg.valuation,
               "rows": {k: len(v) for k, v in T.items()}, "answer_key_rows": {k: len(v) for k, v in K.items()}}
    tables.write(T, K, res.plan, cfg, summary)
    summary["content_hash"] = content_hash(cfg.out_dir)
    return summary


def content_hash(out_dir) -> str:
    digest = hashlib.sha256()
    for f in sorted(Path(out_dir).rglob("*.csv")):
        digest.update(f.relative_to(out_dir).as_posix().encode() + f.read_bytes())
    return digest.hexdigest()[:16]
