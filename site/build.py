#!/usr/bin/env python3
"""Build the Lakefront website, a static site for GitHub Pages.

    pip install -r site/requirements.txt
    python site/build.py                 # writes _site/
    python -m http.server -d _site 8000  # preview at http://localhost:8000

Pages are Markdown files in site/content/, each with a short header between --- lines (title,
nav order, description). The data dictionary is generated from:

- site/dictionary/*.toml: what each table and column means (written by hand);
- samples/synthetic/: which columns each table has, in order, with example values;
- samples/README.md: how many rows each table has in the default build;
- autoins/schema.py: primary and foreign keys.

The build stops with an error if a table or column in the samples has no description, or a
description names a column that no longer exists, so the dictionary cannot drift from the data.
Every page links with paths relative to itself, so the site works at any address, including a
GitHub Pages project site such as https://<owner>.github.io/<repo>/.
"""
from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import json
import math
import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
REPO = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "subwaymatch/auto-insurance-synthetic-data-test")
RELEASE = f"{REPO}/releases/download/latest"
SAMPLES = ROOT / "samples" / "synthetic"

# Which group each table belongs to in the dictionary, in display order.
GROUPS = {
    "Policies and customers": ["policy", "policy_term", "premium_transaction", "quote", "renewal_offer",
                               "customer_contact"],
    "Drivers and vehicles": ["driver", "driver_incident", "insured_vehicle", "vehicle_model_year"],
    "Rating and exposure": ["exposure", "rate_change", "telematics_enrollment", "telematics_score"],
    "Claims": ["claim", "claim_feature", "claim_payment", "claim_reserve_transaction", "coverage", "cause_of_loss",
               "catastrophe", "claim_office", "employee", "vendor"],
    "Billing and distribution": ["billing_invoice", "billing_receipt", "agency", "producer",
                                 "agency_statement", "underwriting_company"],
    "General ledger": ["gl_account", "gl_journal"],
    "Geography": ["location", "zip_demographics"],
    "Answer key (instructors only)": ["policy_truth", "driver_truth", "insured_vehicle_truth", "exposure_truth",
                                      "location_truth", "agency_truth", "claim_feature_truth",
                                      "renewal_offer_truth", "unreported_claim"],
}
ANSWER_KEY = set(GROUPS["Answer key (instructors only)"])

# Repository files that are also pages of the site: links to them stay on the site.
SOURCE_PAGES: dict[str, str] = {}   # e.g. {"docs/limitations.md": "limitations/"} when that page is added

MD_EXTENSIONS = ["tables", "fenced_code", "toc", "attr_list", "md_in_html", "admonition", "footnotes",
                 "sane_lists", "smarty", "def_list"]
MD_CONFIG = {"toc": {"permalink": "#", "permalink_class": "anchor", "permalink_title": "Link to this section",
                     "toc_depth": "2-3"}}


# --------------------------------------------------------------------------- the data dictionary


@dataclass
class Column:
    name: str
    type: str
    description: str
    examples: list[str]
    pk: bool = False
    fk: tuple[str, str] | None = None


@dataclass
class Table:
    name: str
    group: str
    grain: str
    summary: str
    columns: list[Column]
    rows: int | None
    pk: str
    sample_path: str
    references: list[tuple[str, str, str]] = field(default_factory=list)    # (column, table, column)
    referenced_by: list[tuple[str, str, str]] = field(default_factory=list)  # (table, column, column)

    @property
    def answer_key(self) -> bool:
        return self.name in ANSWER_KEY


def load_schema():
    """autoins/schema.py, loaded on its own so the site needs none of the generator's libraries."""
    spec = importlib.util.spec_from_file_location("schema", ROOT / "autoins" / "schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row_counts() -> dict[str, int]:
    """Rows per table in the default build, from the table in samples/README.md."""
    counts = {}
    for line in (ROOT / "samples" / "README.md").read_text().splitlines():
        m = re.match(r"\| \[`(?:answer_key/)?(\w+)\.csv`\]\(synthetic/.*?\) \| [\d,]+ \| ([\d,]+) \|", line)
        if m:
            counts[m.group(1)] = int(m.group(2).replace(",", ""))
    return counts


def column_type(name: str, values: list[str], text_columns: set[str]) -> str:
    """The type the releases give a column (see scripts/release_formats.py), judged from sample values."""
    if name.endswith("_date") or name.startswith("date_"):
        return "date"
    vals = [v for v in values if v != ""]
    if name in text_columns or not vals:
        return "text"
    if set(vals) <= {"Y", "N"}:
        return "Y/N"
    if all(re.fullmatch(r"-?\d+", v) for v in vals):
        return "integer"
    if all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in vals):
        return "decimal"
    return "text"


# Columns whose values the dictionary does not quote as examples.
HIDE_EXAMPLES = {("catastrophe", "note")}


def examples(values: list[str], limit=3, width=36) -> list[str]:
    out = []
    for v in values:
        if v and v not in out:
            out.append(v if len(v) <= width else v[: width - 1] + "…")
        if len(out) == limit:
            break
    return out


def load_dictionary(strict: bool) -> dict[str, Table]:
    schema = load_schema()
    described = {}
    for path in sorted((SITE / "dictionary").glob("*.toml")):
        with path.open("rb") as fh:
            for name, spec in tomllib.load(fh).items():
                if name in described:
                    raise SystemExit(f"{path.name}: table {name} is described twice")
                described[name] = spec
    counts = row_counts()
    problems, tables = [], {}
    grouped = {t: g for g, ts in GROUPS.items() for t in ts}
    sample_files = sorted(SAMPLES.glob("*.csv")) + sorted((SAMPLES / "answer_key").glob("*.csv"))
    for path in sample_files:
        name = path.stem
        with path.open(newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            rows = list(reader)
        spec = described.get(name)
        if spec is None:
            problems.append(f"{name}: no description in site/dictionary/")
            spec = {"grain": "", "summary": "", "columns": {}}
        if name not in grouped:
            problems.append(f"{name}: not in any group (GROUPS in site/build.py)")
        docs = spec.get("columns", {})
        problems += [f"{name}.{c}: no description" for c in header if c not in docs]
        problems += [f"{name}.{c}: described but not a column" for c in docs if c not in header]
        fks = schema.FOREIGN_KEYS.get(name, {})
        pk = schema.PRIMARY_KEYS.get(name, "")
        cols = []
        for i, c in enumerate(header):
            values = [r[i] for r in rows if i < len(r)]
            cols.append(Column(c, column_type(c, values, schema.TEXT_COLUMNS), docs.get(c, ""),
                               [] if (name, c) in HIDE_EXAMPLES else examples(values), pk=(c == pk), fk=fks.get(c)))
        tables[name] = Table(name, grouped.get(name, "Other"), spec.get("grain", ""), spec.get("summary", ""),
                             cols, counts.get(name), pk, path.relative_to(ROOT).as_posix())
    problems += [f"{name}: described but there is no such table" for name in described if name not in tables]
    if problems:
        message = "Data dictionary problems:\n  " + "\n  ".join(problems)
        if strict:
            raise SystemExit(message)
        print("warning: " + message)
    for name, t in tables.items():
        for c in t.columns:
            if c.fk and c.fk[0] in tables:
                t.references.append((c.name, c.fk[0], c.fk[1]))
                tables[c.fk[0]].referenced_by.append((name, c.name, c.fk[1]))
    order = [t for ts in GROUPS.values() for t in ts if t in tables]
    order += [t for t in tables if t not in order]
    return {t: tables[t] for t in order}


# --------------------------------------------------------------------------- the data model diagram

# Hand-placed so that every drawn link joins neighboring columns or runs down one column.
DIAGRAM_COLUMNS = [
    ("Sellers and places", ["underwriting_company", "agency", "producer", "agency_statement", "location",
                            "zip_demographics"]),
    ("Policies and money", ["quote", "policy", "customer_contact", "policy_term", "premium_transaction",
                            "renewal_offer", "billing_invoice", "billing_receipt"]),
    ("Who and what is insured", ["telematics_enrollment", "driver", "driver_incident", "insured_vehicle",
                                 "vehicle_model_year", "exposure", "telematics_score"]),
    ("Claims", ["catastrophe", "claim", "claim_feature", "claim_payment", "claim_reserve_transaction"]),
    ("Staff, vendors and ledger", ["claim_office", "employee", "vendor", "gl_account", "gl_journal"]),
]
DIAGRAM_LINKS = [  # (child, parent): the child's foreign key points to the parent
    ("producer", "agency"), ("agency_statement", "agency"), ("zip_demographics", "location"),
    ("policy", "underwriting_company"), ("policy", "agency"), ("policy", "location"),
    ("quote", "policy"), ("customer_contact", "policy"), ("policy_term", "policy"),
    ("premium_transaction", "policy_term"), ("renewal_offer", "policy_term"),
    ("billing_invoice", "policy_term"), ("billing_receipt", "billing_invoice"),
    ("telematics_enrollment", "policy"), ("driver", "policy"), ("insured_vehicle", "policy"),
    ("exposure", "policy_term"), ("driver_incident", "driver"), ("insured_vehicle", "vehicle_model_year"),
    ("exposure", "insured_vehicle"), ("exposure", "driver"), ("telematics_score", "telematics_enrollment"),
    ("claim", "exposure"), ("claim", "catastrophe"), ("claim_feature", "claim"),
    ("claim_payment", "claim_feature"), ("claim_reserve_transaction", "claim_feature"),
    ("claim", "employee"), ("claim_payment", "vendor"), ("employee", "claim_office"),
    ("gl_journal", "gl_account"),
]


def data_model_svg(tables: dict[str, Table], root: str) -> str:
    box_w, box_h, col_gap, row_gap, top = 214, 38, 52, 20, 44
    pos = {}
    for ci, (_, names) in enumerate(DIAGRAM_COLUMNS):
        x = 8 + ci * (box_w + col_gap)
        for ri, name in enumerate(names):
            pos[name] = (x, top + ri * (box_h + row_gap), ci)
    width = 8 * 2 + len(DIAGRAM_COLUMNS) * box_w + (len(DIAGRAM_COLUMNS) - 1) * col_gap
    height = top + max(len(n) for _, n in DIAGRAM_COLUMNS) * (box_h + row_gap) + 4
    parts = []
    for ci, (label, _) in enumerate(DIAGRAM_COLUMNS):
        x = 8 + ci * (box_w + col_gap)
        parts.append(f'<text class="dm-col" x="{x + 2}" y="20">{html.escape(label)}</text>')
    # Links first, so boxes sit on top of them. Same-column links bulge out on the left by an amount
    # that grows with their length, so parallel ones do not overlap.
    for child, parent in DIAGRAM_LINKS:
        if child not in tables or parent not in tables:
            continue
        cx, cy, cc = pos[child]
        px, py, pc = pos[parent]
        if cc == pc:
            y1, y2 = cy + box_h / 2, py + box_h / 2
            bulge = 14 + 6 * abs(y2 - y1) / (box_h + row_gap)
            d = f"M{cx} {y1}C{cx - bulge} {y1} {cx - bulge} {y2} {px} {y2}"
        else:
            if cc > pc:   # parent on the left
                x1, x2 = cx, px + box_w
            else:
                x1, x2 = cx + box_w, px
            y1, y2 = cy + box_h / 2, py + box_h / 2
            mid = (x1 + x2) / 2
            d = f"M{x1} {y1}C{mid} {y1} {mid} {y2} {x2} {y2}"
        parts.append(f'<path class="dm-link" d="{d}"><title>{child} → {parent}</title></path>')
        ex, ey = (px, py + box_h / 2) if cc == pc else (x2, y2)
        parts.append(f'<circle class="dm-dot" cx="{ex}" cy="{ey}" r="3"/>')
    for name, (x, y, _) in pos.items():
        t = tables.get(name)
        if t is None:
            continue
        rows = f"{t.rows:,} rows" if t.rows else ""
        parts.append(
            f'<a href="{root}data-dictionary/{name}/" class="dm-node"><title>{html.escape(t.grain)}</title>'
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="7"/>'
            f'<text class="dm-name" x="{x + 12}" y="{y + 17}">{name}</text>'
            f'<text class="dm-rows" x="{x + 12}" y="{y + 31}">{rows}</text></a>')
    return (f'<svg class="data-model" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="How the main tables link">{"".join(parts)}</svg>')


# --------------------------------------------------------------------------- the territory map

GEO = SITE / "geo" / "zip_boundaries.geojson"
MAP_LABELS = [  # (text, longitude, latitude, class)
    ("McHenry", -88.47, 42.36, ""), ("Lake", -88.03, 42.36, ""), ("Kane", -88.47, 41.96, ""),
    ("DuPage", -88.10, 41.86, ""), ("Cook", -88.02, 42.11, ""), ("Chicago", -87.69, 41.84, ""),
    ("Will", -88.02, 41.40, ""), ("Kendall", -88.47, 41.60, ""), ("Lake Michigan", -87.64, 42.22, "water"),
]
MAP_PROBLEMS: list[str] = []


def territory_map_html() -> str:
    """The ZIP codes shaded by rating territory, with a toggle, a legend, a tooltip and a table."""
    if not GEO.exists():
        return ""
    geo = json.loads(GEO.read_text())
    zips = [f for f in geo["features"] if f["properties"]["kind"] == "zip"]
    counties = [f for f in geo["features"] if f["properties"]["kind"] == "county"]
    # The map stores each ZIP's territories; they must agree with the data (samples hold the first rows).
    by_zip = {f["properties"]["zip_code"]: f["properties"] for f in zips}
    with (SAMPLES / "location.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            p = by_zip.get(row["zip_code"])
            if p is None or (p["liability_territory"], p["comprehensive_territory"]) != (
                    row["liability_territory"], row["comprehensive_territory"]):
                MAP_PROBLEMS.append(row["zip_code"])

    pts = [c for f in zips for c in _coords(f["geometry"])]
    lon0, lon1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lat0, lat1 = min(p[1] for p in pts), max(p[1] for p in pts)
    cos = math.cos(math.radians((lat0 + lat1) / 2))
    width, pad = 520, 6
    k = (width - 2 * pad) / ((lon1 - lon0) * cos)
    height = (lat1 - lat0) * k + 2 * pad
    xy = lambda lon, lat: (f"{(lon - lon0) * cos * k + pad:.1f}", f"{(lat1 - lat) * k + pad:.1f}")

    def d(geom):
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        return "".join("M" + " ".join(" ".join(xy(*c)) for c in ring) + "Z" for poly in polys for ring in poly)

    cls = lambda t: (int(t[1:]) + 1) // 2      # T01-T02 -> 1 ... T11-T12 -> 6
    parts = []
    for f in zips:
        p = f["properties"]
        parts.append(f'<path class="z" d="{d(f["geometry"])}" data-zip="{p["zip_code"]}" '
                     f'data-place="{html.escape(p["city"])}, {html.escape(p["county"])}" '
                     f'data-l="{p["liability_territory"]}" data-c="{p["comprehensive_territory"]}" '
                     f'data-lc="{cls(p["liability_territory"])}" data-cc="{cls(p["comprehensive_territory"])}"/>')
    parts += [f'<path class="county" d="{d(f["geometry"])}"/>' for f in counties]
    for text, lon, lat, extra in MAP_LABELS:
        x, y = xy(lon, lat)
        parts.append(f'<text class="map-label {extra}" x="{x}" y="{y}" text-anchor="middle">{text}</text>')
    svg = (f'<svg class="terr-map" data-view="liability" viewBox="0 0 {width} {height:.0f}" role="img" '
           f'aria-label="Lakefront’s rating territories by ZIP code">{"".join(parts)}</svg>')

    legend = "".join(f'<li><i class="sw sw{i}"></i>T{2 * i - 1:02d}–T{2 * i:02d}</li>' for i in range(1, 7))
    rows = "".join(
        f'<tr><td>{p["zip_code"]}</td><td>{html.escape(p["city"])}</td><td>{html.escape(p["county"])}</td>'
        f'<td>{p["liability_territory"]}</td><td>{p["comprehensive_territory"]}</td></tr>'
        for p in sorted((f["properties"] for f in zips), key=lambda p: p["zip_code"]))
    return f"""<figure class="terr-figure">
<div class="terr-body">
  <div class="terr-map-wrap">{svg}<div class="map-tip" hidden></div></div>
  <div class="terr-side">
    <div class="map-toggle" role="group" aria-label="Which territories">
      <button type="button" data-view="liability" aria-pressed="true">Liability</button>
      <button type="button" data-view="comprehensive" aria-pressed="false">Comprehensive</button>
    </div>
    <p class="map-note" data-for="liability">Liability territories group ZIP codes by their crash records.</p>
    <p class="map-note" data-for="comprehensive" hidden>Comprehensive territories group ZIP codes by their vehicle-theft records.</p>
    <ol class="map-legend">{legend}</ol>
    <p class="map-scale"><span>Lower hazard</span><span>Higher hazard</span></p>
    <p class="map-note">Each territory holds about the same number of households with a car. Hover over a ZIP code for its territories.</p>
  </div>
</div>
<details class="map-table"><summary>All {len(zips)} ZIP codes and their territories</summary>
<table><thead><tr><th>ZIP code</th><th>City</th><th>County</th><th>Liability</th><th>Comprehensive</th></tr></thead><tbody>{rows}</tbody></table>
</details>
<figcaption>ZIP code boundaries: US Census Bureau, 2020 ZIP Code Tabulation Areas, simplified.</figcaption>
</figure>"""


def _coords(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return [c for poly in polys for ring in poly for c in ring]


# --------------------------------------------------------------------------- pages


@dataclass
class Page:
    source: Path
    url: str                 # "" for the home page, else "name/"
    meta: dict
    body: str                # Markdown

    @property
    def depth(self) -> int:
        return self.url.count("/")


def read_page(path: Path) -> Page:
    text = path.read_text()
    meta = {}
    if text.startswith("---\n"):
        head, text = text[4:].split("\n---\n", 1)
        for line in head.splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    if "source" in meta:   # the body is a file elsewhere in the repository
        src = ROOT / meta["source"]
        body = src.read_text()
        body = re.sub(r"\A# .*\n", "", body)    # the page supplies its own title
        text = text.strip() + "\n\n" + rewrite_repo_links(body, meta["source"])
    url = "" if path.stem == "index" else f"{path.stem}/"
    return Page(path, url, meta, text)


def rewrite_repo_links(body: str, source: str) -> str:
    """Links in a repository Markdown file are relative to it; point them at the site or GitHub."""
    base = Path(source).parent

    def fix(m):
        text, target = m.group(1), m.group(2)
        if re.match(r"[a-z]+:|#|/", target):
            return m.group(0)
        path, _, anchor = target.partition("#")
        resolved = os.path.normpath(base / path).replace(os.sep, "/")
        if resolved in SOURCE_PAGES:
            return f"[{text}](/{SOURCE_PAGES[resolved]}{'#' + anchor if anchor else ''})"
        kind = "tree" if resolved.endswith("/") or "." not in resolved.rsplit("/", 1)[-1] else "blob"
        return f"[{text}]({REPO}/{kind}/main/{resolved}{'#' + anchor if anchor else ''})"

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", fix, body)


def sun_paths() -> dict:
    """The sun and lake shapes of the logo's favicon (brand/logo/favicon.svg), for the home page's large
    sun: the same drawing, colored by the site's own light and dark themes."""
    d = re.findall(r'<path fill="[^"]+" d="([^"]+)"', (ROOT / "brand" / "logo" / "favicon.svg").read_text())
    return {"sky": d[0], "lake": d[1]}


ICON_REF = re.compile(r"%ICON\(([a-z0-9-]+)\)%")


def icon(name: str) -> str:
    """A Lucide icon from site/icons/ (lucide-static, ISC license), inline and hidden from screen readers."""
    svg = (SITE / "icons" / f"{name}.svg").read_text()
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r'\s(width|height)="24"', r' \1="16"', svg)
    svg = re.sub(r"\s+", " ", svg.replace("<svg", '<svg aria-hidden="true"', 1)).strip()
    return svg.replace("> <", "><")


UNKNOWN_REFS: set[str] = set()   # `table.column` in a page where the table has no such column
CODE_REF = re.compile(r"<code>([a-z_]+)(?:\.([a-z_0-9]+))?</code>")
SKIP_BLOCKS = re.compile(r"(<a\b.*?</a>|<pre\b.*?</pre>|<h[1-6]\b.*?</h[1-6]>)", re.S)


def link_code_refs(body: str, tables: dict[str, Table], root: str) -> str:
    """`claim.loss_date` or `policy` in running text becomes a link to the dictionary."""
    def link(m):
        table, col = m.group(1), m.group(2)
        t = tables.get(table)
        if t is None:
            return m.group(0)
        if col and col not in {c.name for c in t.columns}:
            UNKNOWN_REFS.add(f"{table}.{col}")
            return m.group(0)
        href = f"{root}data-dictionary/{table}/" + (f"#{col}" if col else "")
        return f'<a class="ref" href="{href}">{m.group(0)}</a>'

    pieces = SKIP_BLOCKS.split(body)
    return "".join(p if i % 2 else CODE_REF.sub(link, p) for i, p in enumerate(pieces))


def relative_links(body: str, root: str) -> str:
    """Site-absolute links (/data-model/) become relative to the page (../data-model/)."""
    return re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{root}', body)


def render_markdown(text: str) -> tuple[str, list]:
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_CONFIG)
    out = md.convert(text)
    return out, md.toc_tokens


def inline_markdown(text: str) -> str:
    """Markdown for one paragraph or less, without the wrapping <p>."""
    out = markdown.markdown(text, extensions=["smarty"])
    return re.sub(r"\A<p>(.*)</p>\Z", r"\1", out.strip(), flags=re.S)


# --------------------------------------------------------------------------- build


def build(out: Path, base_url: str, strict: bool) -> None:
    tables = load_dictionary(strict)
    env = Environment(loader=FileSystemLoader(SITE / "templates"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["md"] = inline_markdown
    env.globals["icon"] = lambda name: Markup(icon(name))
    env.filters["lower_first"] = lambda s: s[:1].lower() + s[1:] if s[1:2].islower() else s
    pages = [read_page(p) for p in sorted((SITE / "content").glob("*.md"))]
    dictionary_entry = Page(SITE, "data-dictionary/", {"title": "Data dictionary", "nav_title": "Dictionary",
                                                        "nav": "4.5"}, "")
    nav = sorted([p for p in pages if p.meta.get("nav")] + [dictionary_entry], key=lambda p: float(p.meta["nav"]))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    common = dict(repo=REPO, release=RELEASE, groups=GROUPS, base_url=base_url.rstrip("/") + "/" if base_url else "",
                  stats=site_stats(tables), sun=sun_paths(), year=2026)

    def write(url: str, template: str, **ctx):
        # Links are relative to the page, except on the 404 page, which GitHub Pages serves at any address.
        root = ("../" * url.count("/") or "./") if url != "404.html" else (common["base_url"] or "/")
        nav_items = [dict(title=p.meta.get("nav_title", p.meta["title"]), href=root + p.url,
                          active=(p.url == url or (p.url and url.startswith(p.url))),
                          button=p.meta.get("nav_style") == "button")
                     for p in nav]
        html_text = env.get_template(template).render(root=root, url=url, nav=nav_items, **common, **ctx)
        dest = out / url / "index.html" if not url.endswith(".html") else out / url
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(relative_links(html_text, root))

    for page in pages:
        root = "../" * page.depth or "./"
        body = page.body.replace("<!-- table-list -->", table_list_markdown(tables))
        body = body.replace("%RELEASE%", RELEASE).replace("%REPO%", REPO)
        body_html, toc = render_markdown(body)
        body_html = link_code_refs(body_html, tables, root)
        body_html = ICON_REF.sub(lambda m: icon(m.group(1)), body_html)
        body_html = body_html.replace("<!-- territory-map -->", territory_map_html())
        body_html = body_html.replace("<!-- data-model-diagram -->",
                                      f'<figure class="diagram">{data_model_svg(tables, "/")}</figure>')
        layout = page.meta.get("layout", "page")
        write(page.url, f"{layout}.html", page=page.meta, content=body_html, toc=toc, tables=tables)

    write("data-dictionary/", "dictionary.html", page={"title": "Data dictionary",
          "description": "Every table and column in the Lakefront dataset."}, tables=tables,
          search_index=json.dumps([[t.name, c.name, c.type, strip_md(c.description)]
                                   for t in tables.values() for c in t.columns], separators=(",", ":")))
    for t in tables.values():
        write(f"data-dictionary/{t.name}/", "table.html",
              page={"title": t.name, "description": f"{t.grain}: {strip_md(t.summary)}"[:300]}, table=t,
              tables=tables)
    write("404.html", "404.html", page={"title": "Page not found"})

    static = out / "static"
    shutil.copytree(SITE / "static", static)
    logo = ROOT / "brand" / "logo"
    for name in ("lakefront-logo.svg", "lakefront-logo-dark.svg", "social-card.png"):
        if (logo / name).exists():
            shutil.copy(logo / name, static / name)
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        shutil.copy(logo / name, out / name)
    (out / ".nojekyll").write_text("")
    if base_url:
        urls = [p.url for p in pages] + ["data-dictionary/"] + [f"data-dictionary/{t}/" for t in tables]
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{common['base_url']}{u}</loc></url>\n" for u in urls) + "</urlset>\n")
        (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {common['base_url']}sitemap.xml\n")
    if MAP_PROBLEMS:
        message = (f"site/geo/zip_boundaries.geojson disagrees with samples/synthetic/location.csv for ZIP codes "
                   f"{sorted(set(MAP_PROBLEMS))}; rerun site/geo/fetch_zip_boundaries.py with a new build")
        if strict:
            raise SystemExit(message)
        print("warning: " + message)
    if UNKNOWN_REFS:
        message = "Pages name columns that do not exist: " + ", ".join(sorted(UNKNOWN_REFS))
        if strict:
            raise SystemExit(message)
        print("warning: " + message)
    print(f"built {len(pages)} pages and {len(tables)} dictionary tables into {out}")


def strip_md(text: str) -> str:
    return re.sub(r"[`*_]", "", " ".join(text.split()))


def table_list_markdown(tables: dict[str, Table]) -> str:
    lines = []
    for group, names in GROUPS.items():
        present = [tables[n] for n in names if n in tables]
        if not present:
            continue
        lines += [f"**{group}**", "", "| Table | One row per | Rows |", "|---|---|---:|"]
        lines += [f"| `{t.name}` | {t.grain} | {t.rows:,} |" if t.rows else f"| `{t.name}` | {t.grain} | |"
                  for t in present]
        lines.append("")
    return "\n".join(lines)


def site_stats(tables: dict[str, Table]) -> dict:
    rows = lambda t: tables[t].rows if t in tables and tables[t].rows else 0
    data_tables = [t for t in tables if t not in ANSWER_KEY]
    return {"policies": rows("policy"), "claims": rows("claim"), "tables": len(data_tables),
            "columns": sum(len(tables[t].columns) for t in data_tables), "zips": rows("location"),
            "drivers": rows("driver"), "vehicles": rows("insured_vehicle"), "quotes": rows("quote"),
            "models": rows("vehicle_model_year")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "_site")
    ap.add_argument("--base-url", default="", help="the site's address, for the sitemap and social cards")
    ap.add_argument("--no-strict", action="store_true", help="warn about dictionary problems instead of failing")
    args = ap.parse_args()
    build(args.out, args.base_url, strict=not args.no_strict)


if __name__ == "__main__":
    main()
