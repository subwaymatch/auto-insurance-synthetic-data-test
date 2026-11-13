#!/usr/bin/env python3
"""Package a generated dataset into release files.

    python scripts/package_release.py --data output --tag v1.0.0 --validation report.txt --dist dist

Writes to --dist:
  chicago-auto-insurance-data-<tag>.zip        the tables (for students)
  chicago-auto-insurance-answer-key-<tag>.zip  the answer key (for instructors)
  validation-report-<tag>.txt                  output of validate.py
  SHA256SUMS.txt
  release_notes.md                             body for the GitHub release

Zip entries use a fixed timestamp and order, so the same data always gives the same zip bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def write_zip(dest: Path, files: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arcname in sorted(files, key=lambda f: f[1]):
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, src.read_bytes(), compresslevel=9)


def notes(tag: str, summary: dict, report: str, assets: dict[str, int]) -> str:
    lr = re.findall(r"^\s+(\d{4}): .*?loss ratio\s+([\d.]+%)", report, flags=re.M)
    freq = re.findall(r"^\s+(BI|PD|COLL|COMP)\s+[\d,]+\s+([\d.]+)\s+([\d,]+)\s", report, flags=re.M)
    size = re.search(r"([\d,]+) earned car-years, \$([\d,]+) earned premium, ([\d,]+) claims", report)
    passed = "ALL CHECKS PASSED" in report
    out = [f"Synthetic Chicago-area auto insurance dataset, {tag}.", "",
           "| Setting | Value |", "|---|---|",
           f"| Seed | `{summary['seed']}` |", f"| Policies | {summary['policies']:,} |",
           f"| Period | {summary['start']} to {summary['valuation']} |"]
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
    desc = {"data": "The tables. Give this one to students.", "answer-key": "Truth behind the data. Instructors only.",
            "validation": "Full output of `validate.py`.", "SHA256SUMS": "Checksums for the files above."}
    for name, n in assets.items():
        key = next(k for k in desc if k in name)
        human = f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} KB" if n >= 1e3 else f"{n} bytes"
        out.append(f"| `{name}` | {desc[key]} | {human} |")
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
    a = ap.parse_args()
    if a.dist.exists():
        shutil.rmtree(a.dist)
    a.dist.mkdir(parents=True)

    readme = REPO / "README.md"
    tables = [(f, f.name) for f in a.data.glob("*.csv")] + [(a.data / "run_summary.json", "run_summary.json"), (readme, "README.md")]
    key = [(f, f"answer_key/{f.name}") for f in (a.data / "answer_key").iterdir() if f.is_file()]
    data_zip = a.dist / f"chicago-auto-insurance-data-{a.tag}.zip"
    key_zip = a.dist / f"chicago-auto-insurance-answer-key-{a.tag}.zip"
    report = a.dist / f"validation-report-{a.tag}.txt"
    write_zip(data_zip, tables)
    write_zip(key_zip, key)
    shutil.copyfile(a.validation, report)

    sums = a.dist / "SHA256SUMS.txt"
    sums.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (data_zip, key_zip, report)))
    assets = {p.name: p.stat().st_size for p in (data_zip, key_zip, report, sums)}
    summary = json.loads((a.data / "run_summary.json").read_text())
    (a.dist / "release_notes.md").write_text(notes(a.tag, summary, a.validation.read_text(), assets))
    for name, n in assets.items():
        print(f"{name:55s}{n:>12,}")


if __name__ == "__main__":
    main()
