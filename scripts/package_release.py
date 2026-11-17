#!/usr/bin/env python3
"""Package a generated dataset into release files.

    python scripts/package_release.py --data output --tag v1.0.0 --validation report.txt --dist dist --formats csv

Writes to --dist, for each format in --formats (csv, sqlite; see scripts/release_formats.py; default csv):
  chicago-auto-insurance-data-<tag>-<format>.<ext>        the tables (for students)
  chicago-auto-insurance-answer-key-<tag>-<format>.<ext>  the answer key (for instructors)
and once per release:
  validation-report-<tag>.txt                             output of validate.py
  SHA256SUMS.txt
  release_notes.md                                        body for the GitHub release (not uploaded as a file)

Assets use fixed timestamps and order, so the same data always gives the same bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_formats import FORMATS, Bundle  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def notes(tag: str, summary: dict, report: str, assets: dict[str, int], source: str = "") -> str:
    lr = re.findall(r"^\s+(\d{4}): .*?loss ratio\s+([\d.]+%)", report, flags=re.M)
    freq = re.findall(r"^\s+(BI|PD|COLL|COMP)\s+[\d,]+\s+([\d.]+)\s+([\d,]+)\s", report, flags=re.M)
    size = re.search(r"([\d,]+) earned car-years, \$([\d,]+) earned premium, ([\d,]+) claims", report)
    passed = "ALL CHECKS PASSED" in report
    out = [f"Synthetic Chicago-area auto insurance dataset, {tag}.", "",
           "| Setting | Value |", "|---|---|",
           f"| Seed | `{summary['seed']}` |", f"| Policies | {summary['policies']:,} |",
           f"| Period | {summary['start']} to {summary['valuation']} |"]
    if source:
        out.append(f"| Built from commit | `{source[:12]}` |")
    if size:
        out += [f"| Earned car-years | {size.group(1)} |", f"| Earned premium | ${size.group(2)} |",
                f"| Claims | {size.group(3)} |"]
    out += ["", f"**Validation:** {'all checks passed' if passed else 'SOME CHECKS FAILED, see the validation report'}.", ""]
    if lr:
        out += ["Loss ratio by accident year (the last year is partial and not yet fully reported):", "",
                "| " + " | ".join(y for y, _ in lr) + " |", "|" + "---|" * len(lr), "| " + " | ".join(v for _, v in lr) + " |", ""]
    if freq:
        out += ["| Coverage | Claims per 100 car-years | Average paid claim |", "|---|---|---|"]
        out += [f"| {c} | {f} | ${s} |" for c, f, s in freq] + [""]
    out += ["## Files", "", "| File | Contents | Size |", "|---|---|---|"]
    desc = {"-answer-key-": "Truth behind the data. Instructors only.", "-data-": "The tables. Give this one to students.",
            "validation": "Full output of `validate.py`.", "SHA256SUMS": "Checksums for the files above."}
    for name, n in assets.items():
        key = next(k for k in desc if k in name)
        fmt = next((f" ({fn.label})" for f, fn in FORMATS.items() if f"-{f}." in name), "")
        if key == "-answer-key-" and "-sqlite." in name:
            fmt += " The database also holds every data table, linked to the answer key."
        human = f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} KB" if n >= 1e3 else f"{n} bytes"
        out.append(f"| `{name}` | {desc[key]}{fmt} | {human} |")
    out += ["", "Rows per table:", "", "| Table | Rows |", "|---|---|"]
    out += [f"| `{k}` | {v:,} |" for k, v in summary["rows"].items()]
    out += ["", f"Regenerate locally with `python generate.py --seed {summary['seed']} --policies {summary['policies']} "
                f"--start {summary['start']} --valuation {summary['valuation']}`."]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="folder written by generate.py")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--validation", type=Path, required=True, help="saved output of validate.py")
    ap.add_argument("--dist", type=Path, default=Path("dist"))
    ap.add_argument("--formats", default="csv", help=f"comma-separated, from: {', '.join(FORMATS)}")
    ap.add_argument("--source", default="", help="commit the data was built from, shown in the release notes")
    a = ap.parse_args()
    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in FORMATS]
    if unknown or not formats:
        sys.exit(f"unknown or missing format(s) {unknown}; available: {', '.join(FORMATS)}")
    if a.dist.exists():
        shutil.rmtree(a.dist)
    a.dist.mkdir(parents=True)

    key_dir = a.data / "answer_key"
    data = {"tables": {f.stem: f for f in sorted(a.data.glob("*.csv"))},
            "extras": [(a.data / "run_summary.json", "run_summary.json"), (REPO / "README.md", "README.md")]}
    key = {"tables": {f.stem: f for f in sorted(key_dir.glob("*.csv"))},
           "extras": [(f, f.name) for f in sorted(key_dir.iterdir()) if f.is_file() and f.suffix != ".csv"],
           "linked": data["tables"]}     # formats that link tables (SQLite) include the data the answer key refers to
    made = []
    for fmt in formats:
        made.append(FORMATS[fmt](Bundle(f"chicago-auto-insurance-data-{a.tag}-{fmt}", **data), a.dist))
        made.append(FORMATS[fmt](Bundle(f"chicago-auto-insurance-answer-key-{a.tag}-{fmt}", **key), a.dist))
    report = a.dist / f"validation-report-{a.tag}.txt"
    shutil.copyfile(a.validation, report)
    made.append(report)

    sums = a.dist / "SHA256SUMS.txt"
    sums.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in made))
    assets = {p.name: p.stat().st_size for p in made + [sums]}
    summary = json.loads((a.data / "run_summary.json").read_text())
    (a.dist / "release_notes.md").write_text(notes(a.tag, summary, a.validation.read_text(), assets, a.source))
    for name, n in assets.items():
        print(f"{name:55s}{n:>12,}")


if __name__ == "__main__":
    main()
