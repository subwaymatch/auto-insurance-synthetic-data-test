#!/usr/bin/env python3
"""Write the first rows of every CSV file in one or more folders, for browsing on GitHub.

    python scripts/make_samples.py --rows 100 --out samples synthetic=output real_data=real_data

Each NAME=FOLDER pair copies every *.csv under FOLDER (subfolders included, so the answer key comes too) to
OUT/NAME/<same relative path>, keeping the header and the first --rows records. A sample is a byte-for-byte
prefix of its source: delimiter, quoting and line endings are untouched. Records are counted with a CSV
reader, so a quoted field that spans lines never cuts a record in half. OUT/NAME is cleared first, so a file
that no longer exists leaves no stale sample. OUT/README.md lists every sample with its full size.
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
from pathlib import Path

HEADER = """# Sample CSV files

The first {rows} rows of every CSV file, so the data can be browsed on GitHub without downloading anything.
They are written by `.github/workflows/samples.yml` (`scripts/make_samples.py`); do not edit them by hand.

- `synthetic/` is the default build of this repository's generator (`python generate.py`), the same data as the
  `latest` release. `synthetic/answer_key/` is the instructor answer key.
- `real_data/` is the real motor insurance portfolio kept in `real_data/` for comparison (see its README).

Rows are simply the first ones in each file, so samples of different tables do not join up: the first 100
claims belong to policies that are mostly not among the first 100 policies. Download a release for the full
data.
"""


def sniff_delimiter(first_line: str) -> str:
    try:
        return csv.Sniffer().sniff(first_line, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def head(src: Path, dest: Path, rows: int) -> tuple[int, int, int]:
    """Copy the header and the first `rows` records of src to dest. Returns (records copied, total records, columns)."""
    raw = src.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    lines = io.StringIO(text, newline="").readlines()
    consumed = []                                   # raw lines read so far, for an exact byte-for-byte prefix

    def feed():
        for line in lines:
            consumed.append(line)
            yield line

    reader = csv.reader(feed(), delimiter=sniff_delimiter(first))
    header = next(reader, [])
    end, total = None, 0
    for total, _ in enumerate(reader, start=1):
        if total == rows:
            end = len(consumed)
    keep = "".join(lines[: end if end is not None else len(lines)])
    dest.parent.mkdir(parents=True, exist_ok=True)
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    dest.write_bytes(bom + keep.encode("utf-8"))
    return min(rows, total), total, len(header)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("samples"))
    ap.add_argument("sources", nargs="+", metavar="NAME=FOLDER")
    a = ap.parse_args()
    if a.rows < 1:
        ap.error("--rows must be at least 1")
    index = [HEADER.format(rows=a.rows)]
    for spec in a.sources:
        name, _, folder = spec.partition("=")
        folder = Path(folder)
        if not name or not folder.is_dir():
            ap.error(f"{spec!r}: expected NAME=FOLDER with an existing folder")
        target = a.out / name
        if target.exists():
            shutil.rmtree(target)
        files = sorted(folder.rglob("*.csv"), key=lambda p: (len(p.relative_to(folder).parts), str(p)))
        index += [f"\n## {name}\n", "| File | Sample rows | Total rows | Columns |", "|---|---|---|---|"]
        for f in files:
            rel = f.relative_to(folder)
            got, total, cols = head(f, target / rel, a.rows)
            index.append(f"| [`{rel.as_posix()}`]({name}/{rel.as_posix()}) | {got:,} | {total:,} | {cols} |")
            print(f"{name}/{rel.as_posix():55s}{got:>6,} of {total:>10,} rows")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "README.md").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    main()
