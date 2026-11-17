"""File formats a release can be published in.

Each format is one function registered with @register. It receives a Bundle (the tables to package, any tables
they refer to, and extra files such as run_summary.json or README.md) and writes one release asset into `dest`,
returning its path. scripts/package_release.py calls it twice per release: once for the student data and once for
the instructor answer key.

Formats:
  csv     a zip of one CSV file per table, exactly as generate.py wrote them
  sqlite  a zip holding one SQLite database with every table, its primary and foreign keys declared and checked

To add a format:

1. Write the exporter below, e.g.

       @register("parquet", extension="zip", label="Parquet")
       def parquet_zip(bundle: Bundle, dest: Path) -> Path:
           out = dest / f"{bundle.stem}.zip"
           files = []
           for name, df in bundle.frames():
               buf = io.BytesIO()
               df.to_parquet(buf, index=False)          # needs pyarrow
               files.append((buf.getvalue(), f"{name}.parquet"))
           write_zip(out, files + bundle.extra_bytes())
           return out

   Excel (one workbook with a sheet per table, via openpyxl; sheets hold at most 1,048,576 rows) follows the same
   pattern.
2. Add any library it needs to requirements-release.txt (the release workflow installs it).
3. Publish with it: `python scripts/package_release.py ... --formats csv,parquet`, or enter "csv,parquet" as the
   formats input when running the "Release dataset" workflow.

Keep exporters deterministic (fixed timestamps, sorted entries) so the same data gives the same bytes.
"""
from __future__ import annotations

import math
import sqlite3
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from autoins import schema  # noqa: E402

FIXED_TIME = (2026, 1, 1, 0, 0, 0)
FORMATS: dict[str, Callable[["Bundle", Path], Path]] = {}


@dataclass
class Bundle:
    """What goes into one release asset."""
    stem: str                                   # asset file name without extension, e.g. ...-data-v1.0.0-csv
    tables: dict[str, Path]                     # table name -> CSV file written by generate.py
    extras: list[tuple[Path, str]] = field(default_factory=list)   # (file, name inside the asset)
    linked: dict[str, Path] = field(default_factory=dict)          # tables the bundle's tables refer to (for the
                                                                    # answer key: the data tables); not exported
                                                                    # as part of the bundle by formats that
                                                                    # cannot link tables

    def frames(self) -> Iterator[tuple[str, pd.DataFrame]]:
        """Each table as a DataFrame, read so blanks stay missing values and IDs keep their types."""
        for name, path in sorted(self.tables.items()):
            yield name, read_table(path)

    def extra_bytes(self) -> list[tuple[bytes, str]]:
        return [(p.read_bytes(), arc) for p, arc in self.extras]


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False)


def register(name: str, extension: str, label: str | None = None) -> Callable:
    """Register an exporter under a format name (used in --formats and in asset file names)."""
    def deco(fn: Callable[[Bundle, Path], Path]) -> Callable[[Bundle, Path], Path]:
        fn.extension = extension
        fn.label = label or name.upper()
        FORMATS[name] = fn
        return fn
    return deco


def write_zip(dest: Path, files: list[tuple[bytes, str]], level: int = 9) -> None:
    """A zip with a fixed timestamp and sorted entries, so the same content always gives the same bytes."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        for data, arcname in sorted(files, key=lambda f: f[1]):
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compresslevel=level)


# ----------------------------------------------------------------------------------------------- formats
@register("csv", extension="zip", label="CSV")
def csv_zip(bundle: Bundle, dest: Path) -> Path:
    """The CSV files exactly as generate.py wrote them, zipped."""
    out = dest / f"{bundle.stem}.zip"
    write_zip(out, [(p.read_bytes(), f"{name}.csv") for name, p in bundle.tables.items()] + bundle.extra_bytes())
    return out


@register("sqlite", extension="zip", label="SQLite")
def sqlite_zip(bundle: Bundle, dest: Path) -> Path:
    """One SQLite database holding every table, zipped with the extra files. The answer key's database also holds
    the data tables (bundle.linked), so its keys link to them: instructors get the whole dataset in one file."""
    out = dest / f"{bundle.stem}.zip"
    name = bundle.stem.removesuffix("-sqlite") + ".sqlite"
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / name
        write_sqlite({**bundle.linked, **bundle.tables}, db)
        # deflate level 6: a 340 MB database compresses five times faster than at level 9, for 2% more bytes
        write_zip(out, [(db.read_bytes(), name)] + bundle.extra_bytes(), level=6)
    return out


# ----------------------------------------------------------------------------------------------- SQLite
def _column_types(path: Path, df: pd.DataFrame) -> dict[str, str]:
    """SQLite type of each column, from how the CSV writes it: whole numbers are INTEGER (a blank does not make an
    integer column real), numbers with a decimal point REAL, anything else TEXT; ZIP codes are always TEXT."""
    types = {}
    floats = [c for c in df.columns if pd.api.types.is_float_dtype(df[c])]
    raw = pd.read_csv(path, usecols=floats, dtype=str, keep_default_na=False) if floats else None
    for c in df.columns:
        if c in schema.TEXT_COLUMNS or not pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c]):
            types[c] = "TEXT"
        elif pd.api.types.is_integer_dtype(df[c]):
            types[c] = "INTEGER"
        else:
            types[c] = "REAL" if raw[c].str.contains(".", regex=False).any() else "INTEGER"
    return types


def _values(s: pd.Series, kind: str) -> list:
    """A column as Python values sqlite3 can store, with None for blanks."""
    missing = s.isna().to_numpy().tolist()
    if kind == "INTEGER":
        vals = s.fillna(0).astype("int64").to_numpy().tolist()
    elif kind == "REAL":
        vals = s.fillna(0.0).astype("float64").to_numpy().tolist()
    else:
        vals = [str(v) for v in s.fillna("").to_numpy().tolist()]
    return [None if m else v for v, m in zip(vals, missing)]


def _create_table(table: str, types: dict[str, str]) -> str:
    q = lambda x: '"' + x.replace('"', '""') + '"'
    pk = schema.PRIMARY_KEYS[table]
    unique = schema.unique_columns(table)
    lines = []
    for c, t in types.items():
        if c == pk and t == "INTEGER":
            lines.append(f"{q(c)} INTEGER PRIMARY KEY")            # an alias of SQLite's rowid: fast lookups
        else:
            lines.append(f"{q(c)} {t}" + (" NOT NULL" if c == pk else "") + (" UNIQUE" if c in unique else ""))
    if types.get(pk) != "INTEGER":
        lines.append(f"PRIMARY KEY ({q(pk)})")
    for c, (ref, ref_col) in schema.FOREIGN_KEYS.get(table, {}).items():
        lines.append(f"FOREIGN KEY ({q(c)}) REFERENCES {q(ref)} ({q(ref_col)})")
    return f"CREATE TABLE {q(table)} (\n  " + ",\n  ".join(lines) + "\n)"


def write_sqlite(tables: dict[str, Path], dest: Path) -> None:
    """Load every table into a new SQLite database at dest, with primary and foreign keys declared and an index on
    every foreign key. Fails if a reference does not resolve, so a published database is always consistent. The
    same data and SQLite version give the same bytes."""
    order = [t for t in schema.PRIMARY_KEYS if t in tables] + sorted(t for t in tables if t not in schema.PRIMARY_KEYS)
    frames = {t: read_table(tables[t]) for t in order}
    wrong = schema.problems({t: list(df.columns) for t, df in frames.items()})
    if wrong:
        raise ValueError("autoins/schema.py does not match the tables:\n  " + "\n  ".join(wrong))
    if dest.exists():
        dest.unlink()
    con = sqlite3.connect(dest)
    try:
        con.executescript("PRAGMA page_size = 4096; PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;"
                          "PRAGMA foreign_keys = OFF;")
        for t in order:
            df = frames[t]
            types = _column_types(tables[t], df)
            con.execute(_create_table(t, types))
            rows = list(zip(*(_values(df[c], types[c]) for c in df.columns)))
            marks = ", ".join("?" * len(df.columns))
            con.executemany(f'INSERT INTO "{t}" VALUES ({marks})', rows)
            for c in schema.FOREIGN_KEYS.get(t, {}):
                con.execute(f'CREATE INDEX "{t}__{c}" ON "{t}" ("{c}")')
        con.commit()
        broken = con.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise ValueError(f"{len(broken):,} foreign key references do not resolve, e.g. {broken[:5]} "
                             "(table, rowid, referenced table, constraint index)")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        con.execute("VACUUM")
    finally:
        con.close()
