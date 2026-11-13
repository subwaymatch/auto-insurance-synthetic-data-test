#!/usr/bin/env python3
"""Generate the synthetic Chicago-area auto insurance dataset.

    python generate.py                      # default seed, 30,000 policies, writes ./output
    python generate.py --seed 7 --policies 5000 --out /tmp/small

The same seed and options always produce byte-identical files.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path

from autoins import config as C
from autoins.pipeline import generate


def main() -> None:
    d = C.Config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=d.seed)
    ap.add_argument("--policies", type=int, default=d.n_policies, help="distinct policies ever written")
    ap.add_argument("--start", default=d.start, help="first day simulated (YYYY-MM-DD, 2021 or later)")
    ap.add_argument("--valuation", default=d.valuation, help="as-of date of the extract (YYYY-MM-DD, 2026 or earlier)")
    ap.add_argument("--out", type=Path, default=d.out_dir)
    a = ap.parse_args()
    cfg = replace(d, seed=a.seed, n_policies=a.policies, start=a.start, valuation=a.valuation, out_dir=a.out)

    t0 = time.time()
    summary = generate(cfg)
    print(f"wrote {len(summary['rows'])} tables and {len(summary['answer_key_rows'])} answer-key tables "
          f"to {cfg.out_dir} in {time.time() - t0:.0f}s")
    for k, v in summary["rows"].items():
        print(f"  {k:28s}{v:>10,}")
    print(f"content hash: {summary['content_hash']}")


if __name__ == "__main__":
    main()
