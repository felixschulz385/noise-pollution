"""Heuristic `skolenhetskod` reorg-lineage crosswalk.

`Skolenhetsregistret` is a live snapshot, not a panel (see
`src/experiments/sweden/schools.ipynb` §8 for the investigation): no
history endpoint, no predecessor/successor field, and Skolverket's own
2023 hemställan (Dnr 2022:854) confirms more detailed reorganization data
is kept internally but never published via the API ("Registret innehåller
i dag vissa detaljer som inte publiceras i API:et, t.ex. mer detaljerade
uppgifter om omorganisationer"). A school that splits, merges, or gets
renamed shows up in the register as one `Vilande` (retired) unit and a
separate `Aktiv`/`Planerad` unit at the exact same coordinates, with no
official link between them -- even though SIRIS assessment history is
keyed by the same `skolenhetskod` and genuinely splits across old/new IDs
when this happens.

This module resolves the unambiguous, high-confidence subset of that
churn. Within each co-located group that mixes a retiring and an active
unit (145 such groups nationally, checked live), link by normalized-name
similarity (grade-range/`enhet N`/digit/särskola-terminology stripping,
see `norm_name`, then `difflib.SequenceMatcher`), keep only mutual-best
pairs with no tied runner-up, and require `name_sim >= NAME_SIM_THRESHOLD`.
A second guard excludes "bare-digit twins" (`Vasaskolan 1`/`Vasaskolan 2`)
that the digit-stripping normalization would otherwise conflate with a
real rename: both start on the same date and are two separate co-located
units, not a succession -- found live by checking this crosswalk's overlap
with the regression panel (`§9` of the same notebook) and confirmed by
their identical `startdatum`. The remaining ambiguous/low-similarity churn
(anything still below `0.8` after normalization, plus ties) is
deliberately left unresolved here -- see the notebook for why guessing
there does more harm than leaving it alone. Kept as its own stage (not
folded into `preprocess.py`), same isolation reason every other stage in
this pipeline is separate: editing the matching heuristic should never
force a re-fetch/re-geocode, and vice versa.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

from src.regions.sweden.sources.schools.shared import schools_paths

NAME_SIM_THRESHOLD = 0.8
COORD_COLS = ["sweref_e", "sweref_n"]
RETIRING_STATUS = "Vilande"
CANDIDATE_STATUSES = ("Aktiv", "Planerad")


#  Sweden renamed "särskola"/"grundsärskola" (the old special-education
# term) to "anpassad grundskola"/"anpassad gymnasieskola" nationally -- a
# real terminology reform, not a data artifact. A unit whose name only
# differs by this reform (`Vegalyckan särskola` -> `Vegalyckan`,
# `Hagalundskolan Särskola` -> `Hagalundskolan`) is real lineage that
# `norm_name`'s grade-range/digit stripping alone doesn't catch -- found
# live in the `name_sim` 0.5-0.8 "review" band (`schools.ipynb` §8), where
# 8 of 42 links crossed the confident threshold once this was treated as
# an equivalence class, with zero false positives pulled in from the
# already-rejected `< 0.5` band.
_SPECIAL_ED_TERMS = re.compile(
    r"\b(grundsärskol\w*|gymnasiesärskol\w*|anpassad\s+grundskol\w*|anpassad\s+gymnasieskol\w*|särskol\w*)\b"
)

# A standalone token made only of h/l/m letters (any order, up to 3 long) is
# a grade-band marker (lågstadiet/mellanstadiet/högstadiet), the letter-coded
# equivalent of a numeric grade range -- `RONNASKOLAN H` and `Ronnaskolan`
# are the same school, just as `Skolan 7-9` and `Skolan` would be. Found
# live in `schools_lineage.ipynb` §3 while matching SIRIS's 803 vanished
# (pre-registry) codes by name+kommun: 147 of the unresolved 0.9-0.999
# "near-exact" band were exactly this gap. Checked at scale before shipping
# (same notebook): net +10 trusted matches in that population (284 vs 274
# baseline exact+untied matches), only 4 new ties (inspected -- genuine
# same-kommun ambiguity, not false positives), and literally zero effect
# (0 gained, 0 lost) on the already-shipped 40-link within-registry
# crosswalk below, since that matching is coordinate-anchored to a single
# small candidate group rather than an entire kommun. A parallel idea --
# also accepting a bare `F` (no digit) as a range start, e.g. `F-9` -- was
# tested the same way and REFUTED: it's net NEGATIVE (-13) because it
# blindly conflates genuine grade-band *splits* that both currently exist
# (`Braås skola F-3` and `Braås skola 4-9` are two real, separate, active
# units, not two names for one school) -- unlike the h/l/m case, `F-N`
# ranges very commonly denote exactly one half of such a split. Do not
# re-add that fix; see the notebook for the full comparison.
_GRADE_LEVEL_LETTERS = re.compile(r"\b[hlm]{1,3}\b")


def norm_name(name: object) -> str:
    """Strip grade ranges (`7-9`, `F-3`), `enhet N`, any other stray digit,
    the särskola/anpassad-grundskola terminology-reform vocabulary
    (`_SPECIAL_ED_TERMS`), and standalone h/l/m grade-level-letter markers
    (`_GRADE_LEVEL_LETTERS`), so `Älvegårdsskolan F-3` and `Älvegårdsskolan
    1-9` (or `Vegalyckan särskola` and `Vegalyckan`, or `RONNASKOLAN H` and
    `Ronnaskolan`) compare as the same base name. Also strips bare numbered
    suffixes (`Vasaskolan 1`/`Vasaskolan 2`) -- `_is_bare_digit_twin` below
    exists specifically to catch the false positives that causes."""
    text = str(name).lower()
    text = re.sub(r"\b(f|ak|åk|arskurs|årskurs)?\s*\d+\s*[-–]\s*\d+\b", " ", text)
    text = re.sub(r"\benhet\s*\d+\b", " ", text)
    text = _SPECIAL_ED_TERMS.sub(" ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = _GRADE_LEVEL_LETTERS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_bare_digit_twin(old_name: str, new_name: str) -> bool:
    """True when two names are identical except for a single trailing
    number (`Hagaskolan 1` vs `Hagaskolan 2`) -- two co-located sibling
    units, confirmed live to share the same `startdatum`, not a rename.
    `norm_name` strips that digit along with real grade-range suffixes, so
    this check exists to un-collapse the two cases before trusting a
    match."""
    strip_trailing_digit = lambda s: re.sub(r"\s*\d+\s*$", "", str(s)).strip().lower()
    return old_name != new_name and strip_trailing_digit(old_name) == strip_trailing_digit(new_name)


def mixed_status_groups(schools: pd.DataFrame) -> list[pd.DataFrame]:
    """Co-located (exact `sweref_e`/`sweref_n`) groups that mix a
    `Vilande` unit with an `Aktiv`/`Planerad` one -- the ID-churn
    signature. Most co-location is benign (Komvux/SFI/gymnasium units
    sharing one building each keep their own code); this narrower
    signature is what a split/merge/rename reorganization looks like in a
    snapshot register."""
    coords = schools.dropna(subset=COORD_COLS)
    return [
        grp
        for _, grp in coords.groupby(COORD_COLS)
        if len(grp) >= 2
        and (grp["status"] == RETIRING_STATUS).any()
        and grp["status"].isin(CANDIDATE_STATUSES).any()
    ]


def build_lineage_crosswalk(schools: pd.DataFrame) -> pd.DataFrame:
    """High-confidence `old_code -> new_code` links only -- see the module
    docstring for the mutual-best + no-tie + `name_sim >= 0.8` +
    not-a-bare-digit-twin criteria. Every excluded candidate (ambiguous,
    low-similarity, or a bare-digit twin) is left out entirely, not kept
    with a lower-confidence flag: downstream code treats this table as
    "safe to auto-apply", not as a fuller list to filter further."""
    schools = schools.copy()
    schools["name_norm"] = schools["namn"].map(norm_name)
    name_lookup = schools.set_index("skolenhetskod")["namn"]
    huvudman_lookup = schools.set_index("skolenhetskod")["huvudman_orgnr"]

    link_rows = []
    for grp in mixed_status_groups(schools):
        retiring = grp[grp["status"] == RETIRING_STATUS]
        candidates = grp[grp["status"].isin(CANDIDATE_STATUSES)]
        scored = pd.DataFrame(
            [
                {
                    "old_code": r["skolenhetskod"],
                    "new_code": c["skolenhetskod"],
                    "name_sim": SequenceMatcher(None, r["name_norm"], c["name_norm"]).ratio(),
                }
                for _, r in retiring.iterrows()
                for _, c in candidates.iterrows()
            ]
        )
        best_old = scored.loc[scored.groupby("old_code")["name_sim"].idxmax()]
        best_new = scored.loc[scored.groupby("new_code")["name_sim"].idxmax()]
        mutual = best_old.merge(best_new[["old_code", "new_code"]], on=["old_code", "new_code"])

        for _, m in mutual.iterrows():
            old_scores = scored.loc[scored["old_code"] == m["old_code"], "name_sim"].sort_values(ascending=False)
            new_scores = scored.loc[scored["new_code"] == m["new_code"], "name_sim"].sort_values(ascending=False)
            tied = (len(old_scores) > 1 and np.isclose(old_scores.iloc[0], old_scores.iloc[1])) or (
                len(new_scores) > 1 and np.isclose(new_scores.iloc[0], new_scores.iloc[1])
            )
            if not tied:
                link_rows.append(m.to_dict())

    links = pd.DataFrame(link_rows, columns=["old_code", "new_code", "name_sim"])
    if links.empty:
        return links.assign(old_name=pd.Series(dtype=object), new_name=pd.Series(dtype=object))

    links["old_name"] = links["old_code"].map(name_lookup)
    links["new_name"] = links["new_code"].map(name_lookup)

    confident = links[links["name_sim"] >= NAME_SIM_THRESHOLD].copy()
    if confident.empty:
        return confident.sort_values("old_code").reset_index(drop=True)
    twin_risk = confident.apply(lambda r: _is_bare_digit_twin(r["old_name"], r["new_name"]), axis=1)
    return confident[~twin_risk].sort_values("old_code").reset_index(drop=True)


def load_schools_table(root: Path | None = None) -> pd.DataFrame:
    path = schools_paths(root)["processed"] / "schools.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data schools preprocess` first.")
    return pd.read_csv(path, dtype={"skolenhetskod": str})


def lineage_crosswalk_path(root: Path | None = None) -> Path:
    return schools_paths(root)["processed"] / "skolenhetskod_lineage.csv"


def save_lineage_crosswalk(crosswalk: pd.DataFrame, root: Path | None = None) -> str:
    path = lineage_crosswalk_path(root)
    crosswalk.to_csv(path, index=False)
    return str(path)


def load_lineage_crosswalk(root: Path | None = None) -> pd.DataFrame:
    path = lineage_crosswalk_path(root)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run `sweden data schools build-lineage` first.")
    return pd.read_csv(path, dtype={"old_code": str, "new_code": str})


def run_schools_lineage(root: Path | None = None) -> dict[str, object]:
    schools = load_schools_table(root)
    mixed_groups = mixed_status_groups(schools.assign(name_norm=schools["namn"].map(norm_name)))
    crosswalk = build_lineage_crosswalk(schools)
    saved_path = save_lineage_crosswalk(crosswalk, root)
    return {
        "n_schools": int(len(schools)),
        "n_mixed_status_location_groups": len(mixed_groups),
        "n_lineage_links": int(len(crosswalk)),
        "saved": saved_path,
    }
