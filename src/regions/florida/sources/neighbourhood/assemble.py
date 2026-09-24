"""Stage 3 for the Florida `neighbourhood` source: a STATIC school->tract /
school->ZIP spatial match (schools don't move, and boundaries are stable
enough within a vintage — the same "cross-section match, time-varying data
joined on top" shape `traffic/assemble.py` uses for its school->roadway
match), then the two time-varying panels `panel/assemble.py` consumes.

`REQUIRES` `schools preprocess` (`school_cross_section.parquet`) and this
source's own `fetch` + `preprocess`.

**Point-in-polygon, not nearest-line** — the only Florida source so far
doing a polygon-containment spatial join rather than a linear-referencing
one. Primary match is `predicate="within"`; a school that still falls
outside every polygon (the cartographic boundary layers are a generalized
1:500,000 simplification — see `preprocess.py`'s module docstring — so a
coastal or barrier-island school's point can occasionally sit just outside
a simplified shoreline) falls back to nearest-polygon-centroid, not left
unmatched.

**Two tract vintages, resolved per ACS year, not per school.** A school's
`(tract_geoid_2010, tract_geoid_2020)` are both computed once (static), and
`build_school_acs_panel` picks whichever vintage a given ACS year actually
uses (`shared.tract_vintage_for_year`) when joining that year's tract-level
ACS row onto the school.
"""
from __future__ import annotations

import datetime as dt
import json
import warnings
from pathlib import Path

import pandas as pd

# `~geometry.is_empty & geometry.notna()` is geopandas' own recommended
# replacement for the pre-1.0 `.notna()` behaviour (which treated an empty
# geometry as missing too) -- already implemented correctly below, so the
# warning `.notna()` itself still raises is just noise here.
warnings.filterwarnings("ignore", message="GeoSeries.notna", category=UserWarning)

from src.regions.florida.sources.neighbourhood.shared import (
    school_acs_panel_path,
    school_tract_match_path,
    school_zhvi_panel_path,
    school_zip_match_path,
    tract_vintage_for_year,
)
from src.regions.florida.sources.schools.shared import processed_cross_section_path


def placed_school_points(cross_section: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Schools with a real, non-empty geometry. geopandas 1.0+ changed
    `.notna()` to treat an EMPTY geometry (e.g. a degenerate `Point()`) as
    non-null, unlike a real `None` — a plain `.notna()` filter silently let
    unplaced schools through as if they had a real location (caught in this
    module's own first real run: inflated "placed schools" from the real
    5,984 to 7,204). Exclude both explicitly, not just `None`."""
    placed = ~cross_section["geometry"].is_empty & cross_section["geometry"].notna()
    return cross_section.loc[placed, ["msid", "geometry"]].reset_index(drop=True)


def load_school_points(root: Path | None = None) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    path = processed_cross_section_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data schools preprocess` first.")
    return placed_school_points(gpd.read_parquet(path))


def load_processed_tract_boundaries(root: Path | None = None) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    from src.regions.florida.sources.neighbourhood.shared import processed_tract_boundaries_path

    path = processed_tract_boundaries_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data neighbourhood preprocess` first.")
    return gpd.read_parquet(path)


def load_processed_zcta_boundaries(root: Path | None = None) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    from src.regions.florida.sources.neighbourhood.shared import processed_zcta_boundaries_path

    path = processed_zcta_boundaries_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data neighbourhood preprocess` first.")
    return gpd.read_parquet(path)


def load_processed_acs(root: Path | None = None) -> pd.DataFrame:
    from src.regions.florida.sources.neighbourhood.shared import processed_acs_path

    path = processed_acs_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data neighbourhood preprocess` first.")
    return pd.read_parquet(path)


def load_processed_zhvi(root: Path | None = None) -> pd.DataFrame:
    from src.regions.florida.sources.neighbourhood.shared import processed_zhvi_path

    path = processed_zhvi_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — run `... florida data neighbourhood preprocess` first.")
    return pd.read_parquet(path)


def _sjoin_within_then_nearest(points: "gpd.GeoDataFrame", polygons: "gpd.GeoDataFrame", id_col: str) -> pd.DataFrame:
    import geopandas as gpd

    within = gpd.sjoin(points[["msid", "geometry"]], polygons[[id_col, "geometry"]], predicate="within", how="left")
    within = within.drop(columns="index_right").drop_duplicates(subset="msid", keep="first")

    unmatched = within[within[id_col].isna()]
    if not unmatched.empty:
        nearest = gpd.sjoin_nearest(
            points.loc[points["msid"].isin(unmatched["msid"]), ["msid", "geometry"]],
            polygons[[id_col, "geometry"]],
            how="left",
        ).drop(columns="index_right").drop_duplicates(subset="msid", keep="first")
        within = pd.concat([within[within[id_col].notna()], nearest], ignore_index=True)

    return pd.DataFrame(within[["msid", id_col]])


def build_school_tract_match(points: "gpd.GeoDataFrame", tract_boundaries: "gpd.GeoDataFrame") -> pd.DataFrame:
    """One row per `(msid, tract_vintage)` — every placed school matched
    against BOTH tract-boundary vintages present in `tract_boundaries`."""
    columns = ["msid", "tract_vintage", "tract_geoid"]
    if points.empty or tract_boundaries.empty:
        return pd.DataFrame(columns=columns)

    frames = []
    for vintage, group in tract_boundaries.groupby("tract_vintage"):
        matched = _sjoin_within_then_nearest(points, group, "tract_geoid")
        matched["tract_vintage"] = vintage
        frames.append(matched)
    return pd.concat(frames, ignore_index=True)[columns]


def build_school_zip_match(points: "gpd.GeoDataFrame", zcta_boundaries: "gpd.GeoDataFrame") -> pd.DataFrame:
    """One row per `msid` — every placed school matched to its containing
    (or nearest) ZCTA."""
    columns = ["msid", "zip_code"]
    if points.empty or zcta_boundaries.empty:
        return pd.DataFrame(columns=columns)
    return _sjoin_within_then_nearest(points, zcta_boundaries, "zip_code")[columns]


def build_school_acs_panel(school_tract_match: pd.DataFrame, acs: pd.DataFrame) -> pd.DataFrame:
    """One row per `(msid, year)` for every ACS year present — each year
    joined via whichever tract vintage `tract_vintage_for_year` says that
    year actually uses."""
    columns = [
        "msid", "year", "median_household_income", "poverty_rate",
        "pct_owner_occupied", "pct_bachelors_plus", "pct_moved_last_year",
    ]
    if acs.empty or school_tract_match.empty:
        return pd.DataFrame(columns=columns)

    acs = acs.copy()
    acs["tract_vintage"] = acs["year"].apply(tract_vintage_for_year)
    frames = []
    for vintage, acs_year_group in acs.groupby("tract_vintage"):
        matches = school_tract_match[school_tract_match["tract_vintage"] == vintage]
        joined = matches.merge(acs_year_group, on="tract_geoid", how="inner")
        frames.append(joined)
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns].sort_values(["msid", "year"]).reset_index(drop=True)


def build_school_zhvi_panel(school_zip_match: pd.DataFrame, zhvi: pd.DataFrame) -> pd.DataFrame:
    """One row per `(msid, year)` for every ZHVI year present."""
    columns = ["msid", "year", "zhvi"]
    if zhvi.empty or school_zip_match.empty:
        return pd.DataFrame(columns=columns)
    joined = school_zip_match.merge(zhvi, on="zip_code", how="inner")
    return joined[columns].sort_values(["msid", "year"]).reset_index(drop=True)


def save_assembled(
    school_tract_match: pd.DataFrame,
    school_zip_match: pd.DataFrame,
    school_acs_panel: pd.DataFrame,
    school_zhvi_panel: pd.DataFrame,
    root: Path | None = None,
) -> dict[str, str]:
    tract_match_path = school_tract_match_path(root)
    zip_match_path = school_zip_match_path(root)
    acs_panel_path = school_acs_panel_path(root)
    zhvi_panel_path = school_zhvi_panel_path(root)
    for path in (tract_match_path, zip_match_path, acs_panel_path, zhvi_panel_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    school_tract_match.to_parquet(tract_match_path, index=False)
    school_zip_match.to_parquet(zip_match_path, index=False)
    school_acs_panel.to_parquet(acs_panel_path, index=False)
    school_zhvi_panel.to_parquet(zhvi_panel_path, index=False)
    return {
        "school_tract_match": str(tract_match_path),
        "school_zip_match": str(zip_match_path),
        "school_acs_panel": str(acs_panel_path),
        "school_zhvi_panel": str(zhvi_panel_path),
    }


def run_neighbourhood_assemble(root: Path | None = None) -> dict[str, object]:
    points = load_school_points(root)
    tract_boundaries = load_processed_tract_boundaries(root)
    zcta_boundaries = load_processed_zcta_boundaries(root)
    acs = load_processed_acs(root)
    zhvi = load_processed_zhvi(root)

    school_tract_match = build_school_tract_match(points, tract_boundaries)
    school_zip_match = build_school_zip_match(points, zcta_boundaries)
    school_acs_panel = build_school_acs_panel(school_tract_match, acs)
    school_zhvi_panel = build_school_zhvi_panel(school_zip_match, zhvi)
    saved = save_assembled(school_tract_match, school_zip_match, school_acs_panel, school_zhvi_panel, root)

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "src/regions/florida/sources/neighbourhood/assemble.py",
        "placed_schools": int(points["msid"].nunique()),
        "schools_matched_to_tract": int(school_tract_match["msid"].nunique()),
        "schools_matched_to_zip": int(school_zip_match["msid"].nunique()),
        "school_acs_panel_rows": int(len(school_acs_panel)),
        "school_zhvi_panel_rows": int(len(school_zhvi_panel)),
        "saved": saved,
    }
