"""Stage: export `grid_treatment_protected.parquet` as a ready-to-use CSV
plus its Markdown documentation, by default to the project's shared Dropbox
(`SHARED_EXPORT_DIR`), for coauthors merging register residences on the
100m cell code.

REQUIRES `grid assemble` and `barrier-protection build`. The CSV keeps only
cells that are treated, in a control band, or undecided for at least one
barrier kind; every other residence is untreated and outside every band,
so the file stays small. The documentation's numbers are computed from the
exported rows on every run, so the two never disagree.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.core.barrier_geometry.protection import (
    CONTROL_MAX_LATERAL_M,
    PROTECTED_MAX_LATERAL_M,
    PROTECTED_SPAN_MARGIN_M,
)
from src.regions.sweden.sources.barrier_protection.shared import load_barrier_references
from src.regions.sweden.sources.grid.shared import BUFFER_M, SHARED_EXPORT_DIR, assembled_dir
from src.regions.sweden.sources.noise_barriers.shared import BARRIER_KINDS, load_noise_barriers

CSV_NAME = "grid_treatment_protected.csv"
DOC_NAME = "grid_treatment_protected.md"
COLUMNS = (
    "treated", "treat_year", "timing_unknown", "side_unknown",
    "control_band", "control_year", "control_band_unknown",
)
YEARS = ("treat_year", "control_year")
# A cell is exported when any of these is set for any kind.
KEEP_FLAGS = ("treated", "side_unknown", "control_band", "control_band_unknown")


def load_treatment(root: Path | None = None) -> pd.DataFrame:
    path = assembled_dir(root) / "grid_treatment_protected.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data grid assemble` first.")
    return pd.read_parquet(path)


def build_export_table(treatment: pd.DataFrame, kinds: tuple[str, ...] = BARRIER_KINDS) -> pd.DataFrame:
    """The rows and types of the shared CSV: cells with any of `KEEP_FLAGS`
    for at least one kind, flags as 0/1, years as nullable integers (blank
    in the CSV), sorted by `cell_id`. `sweref_e`/`sweref_n` repeat the code's
    two halves as integers, the register's own residence variables."""
    if not treatment["cell_id"].is_unique:
        raise ValueError("cell_id is not unique in grid_treatment_protected.parquet")
    if not treatment["cell_id"].str.fullmatch(r"\d{13}").all():
        raise ValueError("cell_id is not SCB's 13-digit code everywhere -- re-run `sweden data grid preprocess`.")
    keep = treatment[[f"{kind}_{flag}" for kind in kinds for flag in KEEP_FLAGS]].any(axis=1)
    out = treatment.loc[keep, ["cell_id"]].copy()
    out["sweref_e"] = out["cell_id"].str[:6].astype("int32")
    out["sweref_n"] = out["cell_id"].str[6:].astype("int32")
    for kind in kinds:
        for column in COLUMNS:
            out[f"{kind}_{column}"] = treatment.loc[keep, f"{kind}_{column}"].astype("Int16" if column in YEARS else "int8")
    return out.sort_values("cell_id").reset_index(drop=True)


def barrier_side_status(kind: str, root: Path | None = None) -> dict:
    """How many of `kind`'s barriers have no construction year, and how
    many still have no known side (and of those, how many are dated)."""
    barriers = load_noise_barriers(kind, root)
    refs = load_barrier_references(kind, root, barriers_gdf=barriers)
    dated = barriers["built_year"].notna().to_numpy()
    side_unknown = refs.table["side_method"].eq("unknown").to_numpy()
    return {
        "n_barriers": int(len(barriers)),
        "n_undated": int((~dated).sum()),
        "n_side_unknown": int(side_unknown.sum()),
        "n_side_unknown_dated": int((side_unknown & dated).sum()),
    }


def _n(value: int) -> str:
    return f"{value:,}"


def render_doc(
    table: pd.DataFrame, n_grid_cells: int, barriers: dict[str, dict], *, generated: date, assembled: date
) -> str:
    kinds = tuple(barriers)
    stats = {
        kind: {
            "treated": int(table[f"{kind}_treated"].sum()),
            "with_year": int(table[f"{kind}_treat_year"].notna().sum()),
            "timing_unknown": int(table[f"{kind}_timing_unknown"].sum()),
            "side_unknown": int(table[f"{kind}_side_unknown"].sum()),
            "control_band": int(table[f"{kind}_control_band"].sum()),
            "control_with_year": int(table[f"{kind}_control_year"].notna().sum()),
            "control_band_unknown": int(table[f"{kind}_control_band_unknown"].sum()),
            "first": table[f"{kind}_treat_year"].min(),
            "last": table[f"{kind}_treat_year"].max(),
        }
        for kind in kinds
    }
    n_both = int(table[[f"{kind}_treated" for kind in kinds]].all(axis=1).sum())

    def row(label: str, key: str) -> str:
        return f"| {label} | " + " | ".join(_n(stats[k][key]) for k in kinds) + " |"

    def barrier_row(label: str, key: str) -> str:
        return f"| {label} | " + " | ".join(_n(barriers[k][key]) for k in kinds) + " |"

    header = "| | " + " | ".join(kinds) + " |\n|---|" + "---:|" * len(kinds)
    years = ", ".join(f"{k} {stats[k]['first']}–{stats[k]['last']}" for k in kinds)
    margin, lateral = int(PROTECTED_SPAN_MARGIN_M), int(PROTECTED_MAX_LATERAL_M)
    control, extent = int(CONTROL_MAX_LATERAL_M), f"{BUFFER_M / 1000:g}"
    flags = " ///\n                     ".join(
        " ".join(f"{k}_{c}" for c in COLUMNS if c not in YEARS) for k in kinds
    )
    n_open = sum(barriers[k]["n_side_unknown"] for k in kinds)
    audit = (
        f"The barrier sides come from a manual audit of aerial imagery; {_n(n_open)}\n"
        "barriers' sides are still unknown (see \"Known gaps\")."
        if n_open
        else "The barrier sides come from a manual audit of aerial imagery."
    )
    sides = (
        "- **Sides.** The barriers whose side is still unknown cause the\n"
        "  `side_unknown` and `control_band_unknown` cells. Once they are\n"
        "  classified by hand, each such cell becomes treated, a control-band\n"
        "  cell or a plain control. Undated barriers among them can only add\n"
        "  cells with unknown timing.\n"
        if n_open
        else ""
    )

    return f"""# Sweden 100 m grid: noise-barrier treatment

`{CSV_NAME}` says, for each 100 m grid cell, whether a road
or rail noise barrier protects it and since when, and which unprotected
cells lie further behind a barrier (its control band). Join it to register
residences on their 100 m cell code.

Generated {generated.isoformat()} from the grid assembled on {assembled.isoformat()}.
{audit}

## Grid key

`sweref_e` and `sweref_n` are the easting and northing of the cell's
**lower-left (south-west) corner** in SWEREF 99 TM (EPSG:3006), integers
ending in 00: the same variables, with the same meaning, as the residence
coordinates on the server. Merge on the two of them as they are, with no
shift.

`cell_id` holds the same corner as SCB's 13-digit code: the 6-digit
easting, then the 7-digit northing, e.g. `3182006374200`. Read it as a
string if you use it; a Stata `float` can't hold 13 digits.

## Treatment and control band

A barrier **protects** a cell when the cell's centre lies:

- on the same side of the road or railway as the barrier (both sides if
  there are walls on both sides),
- beside the barrier's own stretch, up to {margin} m past either end,
- within {lateral} m of the road or track.

A cell can be protected by several barriers. Its treatment year is the
earliest construction year among them, from Trafikverket's barrier
registers.

A cell is in a barrier's **control band** when it meets the first two
conditions but lies {lateral}–{_n(control)} m from the road or track: behind the same
wall, too far away to be shielded. This is the comparison group of a
within-barrier design (Moretti & Wheeler 2025 compare homes 0–500 m and
500–1,500 m behind the same wall). A cell protected by another barrier of
the same kind is treated, not control band. Its control year is the
earliest construction year among the barriers whose band it lies in: the
date to compare it at.

Road and rail are kept separate: a cell can be treated by one kind and in
the other kind's control band.

## Rows

The grid covers every 100 m cell within {extent} km of a road or rail noise
barrier ({_n(n_grid_cells)} cells). The file keeps the **{_n(len(table))} cells**
that are treated, in a control band, or undecided for at least one kind:

{header}
{row("treated", "treated")}
{row("&nbsp;&nbsp;with an exact treatment year", "with_year")}
{row("&nbsp;&nbsp;timing unknown", "timing_unknown")}
{row("untreated, side unknown", "side_unknown")}
{row("control band", "control_band")}
{row("&nbsp;&nbsp;with an exact control year", "control_with_year")}
{row("control band, side unknown", "control_band_unknown")}

For each kind, a cell is in at most one of treated, side unknown, control
band and control band with side unknown. {_n(n_both)} cells are treated by
both kinds.

**A residence whose code is not in the file is untreated and outside every
control band, for both kinds.** It is more than {extent} km from every
barrier, or near one but on the wrong side of its road, beyond the ends of
its stretch, or more than {_n(control)} m from the road. After merging,
set the missing 0/1 flags to 0. Leave the years missing.

## Columns

Each variable appears once for road barriers (`road_`) and once for rail
barriers (`rail_`).

| Column | Meaning |
|---|---|
| `cell_id` | SCB 13-digit cell code (see "Grid key") |
| `sweref_e` | Easting of the cell's lower-left corner, SWEREF 99 TM |
| `sweref_n` | Northing of the cell's lower-left corner, SWEREF 99 TM |
| `{{kind}}_treated` | 1 if a barrier of this kind protects the cell |
| `{{kind}}_treat_year` | First year the cell is protected. Blank if untreated or if the timing is unknown, so every year given is exact |
| `{{kind}}_timing_unknown` | 1 if treated, but a protecting barrier has no construction year. Keep these cells out of designs that use the timing; they can count as ever-treated in robustness checks |
| `{{kind}}_side_unknown` | 1 if untreated, but a barrier whose side we don't know would protect it. **Not a clean control**: drop these cells from the control group |
| `{{kind}}_control_band` | 1 if untreated and in the control band of a barrier of this kind |
| `{{kind}}_control_year` | Earliest construction year among the barriers whose band the cell lies in. Blank if not in a band, or if one of those barriers is undated |
| `{{kind}}_control_band_unknown` | 1 if none of the above, but in the band of a barrier whose side we don't know. Not a clean control-band cell |

Treatment years run {years}. Years before your data
starts are left as they are.

## Merging in Stata

```stata
import delimited using "{CSV_NAME}", stringcols(1) clear
tempfile grid
save `grid'

use residences, clear   // sweref_e, sweref_n: the residence's 100 m cell
merge m:1 sweref_e sweref_n using `grid', keep(master match) nogenerate
foreach v of varlist {flags} {{
    replace `v' = 0 if missing(`v')
}}
```

## Known gaps

{header}
{barrier_row("barriers", "n_barriers")}
{barrier_row("&nbsp;&nbsp;without a construction year", "n_undated")}
{barrier_row("&nbsp;&nbsp;side still unknown", "n_side_unknown")}
{barrier_row("&nbsp;&nbsp;&nbsp;&nbsp;of which dated", "n_side_unknown_dated")}

{sides}- **Years.** A treated cell's year can still move if a barrier whose side
  is unknown also protects it and is older or undated.
- **Construction years.** Missing for many barriers in Trafikverket's
  registers, which is why `timing_unknown` and blank control years are
  common. We are working on filling them.
- **Control band.** A band cell is judged against the barrier's own road
  only. Far out, it may be nearer another road, whose noise it hears
  instead. The band starts right at {lateral} m, where a cell may still be
  partly shielded.
- **Cell centre vs. residence.** Treatment is judged at the cell centre.
  For 13–18% of residences near a protected area, the residence itself
  would get a different status from its cell, as often in one direction
  as in the other.
- **Barriers outside the registers.** At least 350 noise barriers mapped in
  OpenStreetMap are not in Trafikverket's registers and are ignored.
"""


def run_grid_export(
    *, out_dir: Path = SHARED_EXPORT_DIR, kinds: tuple[str, ...] = BARRIER_KINDS, root: Path | None = None
) -> dict:
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        raise FileNotFoundError(f"{out_dir} does not exist -- pass --out-dir, or check the Dropbox is synced.")
    treatment = load_treatment(root)
    table = build_export_table(treatment, kinds)
    barriers = {kind: barrier_side_status(kind, root) for kind in kinds}
    parquet_path = assembled_dir(root) / "grid_treatment_protected.parquet"
    assembled = date.fromtimestamp(parquet_path.stat().st_mtime)

    csv_path = out_dir / CSV_NAME
    doc_path = out_dir / DOC_NAME
    table.to_csv(csv_path, index=False)
    doc_path.write_text(
        render_doc(table, len(treatment), barriers, generated=date.today(), assembled=assembled), encoding="utf-8"
    )
    return {
        "n_grid_cells": int(len(treatment)),
        "n_rows": int(len(table)),
        "barriers": barriers,
        "csv_path": str(csv_path),
        "doc_path": str(doc_path),
    }
