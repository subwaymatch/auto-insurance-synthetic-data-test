"""File formats a release can be published in.

Each format is one function registered with @register. It receives a Bundle (the tables to package and
any extra files such as run_summary.json or README.md) and writes one release asset into `dest`,
returning its path. scripts/package_release.py calls it twice per release: once for the student data
and once for the instructor answer key.

To add a format:

1. Write the exporter below, e.g.

       @register("parquet", extension="zip")
       def parquet_zip(bundle: Bundle, dest: Path) -> Path:
           out = dest / f"{bundle.stem}.zip"
           files = []
           for name, df in bundle.frames():
               buf = io.BytesIO()
               df.to_parquet(buf, index=False)          # needs pyarrow
               files.append((buf.getvalue(), f"{name}.parquet"))
           write_zip(out, files + bundle.extra_bytes())
           return out

   SQLite (one .sqlite file with a table per CSV, via sqlite3 and DataFrame.to_sql) and Excel (one
   workbook with a sheet per table, via openpyxl; sheets hold at most 1,048,576 rows) follow the
   same pattern.
2. Add any library it needs to requirements-release.txt (the release workflow installs it).
3. Publish with it: `python scripts/package_release.py ... --formats csv,parquet`, or enter
   "csv,parquet" as the formats input when running the "Release dataset" workflow.

Keep exporters deterministic (fixed timestamps, sorted entries) so the same data gives the same bytes.
"""
from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

FIXED_TIME = (2026, 1, 1, 0, 0, 0)
FORMATS: dict[str, Callable[["Bundle", Path], Path]] = {}


@dataclass
class Bundle:
    """What goes into one release asset."""
    stem: str                                   # asset file name without extension, e.g. ...-data-v1.0.0-csv
    tables: dict[str, Path]                     # table name -> CSV file written by generate.py
    extras: list[tuple[Path, str]] = field(default_factory=list)   # (file, name inside the asset)

    def frames(self) -> Iterator[tuple[str, pd.DataFrame]]:
        """Each table as a DataFrame, read so blanks stay missing values and IDs keep their types."""
        for name, path in sorted(self.tables.items()):
            yield name, read_table(path)

    def extra_bytes(self) -> list[tuple[bytes, str]]:
        return [(p.read_bytes(), arc) for p, arc in self.extras]


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False)


def register(name: str, extension: str) -> Callable:
    """Register an exporter under a format name (used in --formats and in asset file names)."""
    def deco(fn: Callable[[Bundle, Path], Path]) -> Callable[[Bundle, Path], Path]:
        fn.extension = extension
        FORMATS[name] = fn
        return fn
    return deco


def write_zip(dest: Path, files: list[tuple[bytes, str]]) -> None:
    """A zip with a fixed timestamp and sorted entries, so the same content always gives the same bytes."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for data, arcname in sorted(files, key=lambda f: f[1]):
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compresslevel=9)


# ----------------------------------------------------------------------------------------------- formats
@register("csv", extension="zip")
def csv_zip(bundle: Bundle, dest: Path) -> Path:
    """The CSV files exactly as generate.py wrote them, zipped."""
    out = dest / f"{bundle.stem}.zip"
    write_zip(out, [(p.read_bytes(), f"{name}.csv") for name, p in bundle.tables.items()] + bundle.extra_bytes())
    return out
