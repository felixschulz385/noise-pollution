"""Pure-function tests for the schools `build-lineage` stage -- no network,
no geopandas (works off `schools.csv`-shaped plain-pandas data). See
`src/regions/sweden/sources/schools/lineage.py`'s module docstring and
`src/experiments/sweden/schools.ipynb` §8-9 for the heuristic this
crosswalk implements and why each guard (mutual-best, no ties,
`name_sim >= 0.8`, no bare-digit twins) exists."""
import pandas as pd
import pytest

from src.regions.sweden.sources.schools import lineage


def _school(code, namn, status, huvudman="1", e=100.0, n=200.0):
    return {
        "skolenhetskod": code,
        "namn": namn,
        "status": status,
        "huvudman_orgnr": huvudman,
        "sweref_e": e,
        "sweref_n": n,
    }


def test_norm_name_strips_grade_ranges_enhet_and_digits():
    assert lineage.norm_name("Älvegårdsskolan 4-9") == lineage.norm_name("Älvegårdsskolan 1-9")
    assert lineage.norm_name("Hallernaskolan 7-9 enhet 2") == lineage.norm_name("Hallernaskolan enhet 1")


def test_norm_name_treats_grade_level_letters_as_equivalent_to_a_range():
    """H/M/L (any order, e.g. `LMH`) are the letter-coded equivalent of a
    numeric grade range (högstadiet/mellanstadiet/lågstadiet) -- found live
    while matching SIRIS's 803 vanished (pre-registry) codes by name+kommun
    (`schools_lineage.ipynb` §3-4): `RONNASKOLAN H` and `Ronnaskolan` are
    the same school. Checked at scale before shipping: net +10 trusted
    matches in that population, zero effect on the within-registry
    crosswalk below. A parallel `F-N` (bare `F` range start, no digit) fix
    was tested the same way and REFUTED -- net -13, since it blindly
    conflates genuine currently-active grade-band splits
    (`Skolan F-3`/`Skolan 4-9`) into one name. Not implemented; see the
    notebook."""
    assert lineage.norm_name("RONNASKOLAN H") == lineage.norm_name("Ronnaskolan")
    assert lineage.norm_name("Sånnaskolan LM") == lineage.norm_name("Sånnaskolan M")
    assert lineage.norm_name("Spängerskolan MH") == lineage.norm_name("Spängerskolan LMH")
    # a real word that happens to spell out h/l/m letters is untouched --
    # the guard is a whole-token match only, not a substring strip.
    assert lineage.norm_name("Malmö skola") == "malmö skola"


def test_norm_name_treats_sarskola_terminology_reform_as_equivalent():
    """Sweden renamed "särskola"/"grundsärskola" to "anpassad grundskola"/
    "anpassad gymnasieskola" nationally -- a real reform, not a rename a
    school chose. Found live in the 0.5-0.8 review band (schools.ipynb
    §8): 8 of 42 links were genuine lineage hidden behind this vocabulary
    change alone."""
    assert lineage.norm_name("Vegalyckan särskola") == lineage.norm_name("Vegalyckan")
    assert lineage.norm_name("Hagalundskolan Särskola") == lineage.norm_name("Hagalundskolan")
    assert lineage.norm_name("Rydsbergsskolan grundsärskola") == lineage.norm_name("Rydsbergsskolan")
    assert lineage.norm_name("Herrgårdsgymnasiet") == lineage.norm_name("Herrgårdsgymnasiet anpassad gymnasieskola")


def test_bare_digit_twin_detects_numbered_siblings_not_grade_ranges():
    assert lineage._is_bare_digit_twin("Vasaskolan 1", "Vasaskolan 2")
    assert lineage._is_bare_digit_twin("Hagaskolan 1", "Hagaskolan 2")
    # A grade-range difference is a real reorg signal, not a bare-digit twin.
    assert not lineage._is_bare_digit_twin("Älvegårdsskolan F-3", "Älvegårdsskolan 1-9")
    assert not lineage._is_bare_digit_twin("Same Name", "Same Name")


def test_mixed_status_groups_requires_retiring_and_active_at_same_coords():
    schools = pd.DataFrame(
        [
            _school("1", "A", "Vilande", e=1, n=1),
            _school("2", "A", "Aktiv", e=1, n=1),
            _school("3", "B", "Aktiv", e=2, n=2),  # alone at its own site -- no group
            _school("4", "C", "Vilande", e=3, n=3),
            _school("5", "C", "Vilande", e=3, n=3),  # two retiring, no active -- not a churn signature
        ]
    )
    groups = lineage.mixed_status_groups(schools)
    assert len(groups) == 1
    assert set(groups[0]["skolenhetskod"]) == {"1", "2"}


def test_build_lineage_crosswalk_links_a_real_grade_band_reorg():
    schools = pd.DataFrame(
        [
            _school("old1", "Älvegårdsskolan F-3", "Vilande", e=1, n=1),
            _school("new1", "Älvegårdsskolan 1-9", "Aktiv", e=1, n=1),
        ]
    )
    crosswalk = lineage.build_lineage_crosswalk(schools)
    assert list(crosswalk["old_code"]) == ["old1"]
    assert list(crosswalk["new_code"]) == ["new1"]
    assert crosswalk.loc[0, "name_sim"] >= lineage.NAME_SIM_THRESHOLD


def test_build_lineage_crosswalk_links_a_sarskola_terminology_reform():
    schools = pd.DataFrame(
        [
            _school("old1", "Vegalyckan särskola", "Vilande", e=1, n=1),
            _school("new1", "Vegalyckan", "Aktiv", e=1, n=1),
        ]
    )
    crosswalk = lineage.build_lineage_crosswalk(schools)
    assert list(crosswalk["old_code"]) == ["old1"]
    assert list(crosswalk["new_code"]) == ["new1"]
    assert crosswalk.loc[0, "name_sim"] == 1.0


def test_build_lineage_crosswalk_excludes_bare_digit_twins():
    """`Vasaskolan 1`/`Vasaskolan 2` are two co-located sibling units, not
    a rename -- found live by checking the crosswalk's overlap with the
    regression panel (notebook §9): both start on the same date. Must NOT
    appear in the crosswalk even though normalized-name similarity is 1.0."""
    schools = pd.DataFrame(
        [
            _school("old1", "Vasaskolan 2", "Vilande", e=1, n=1),
            _school("new1", "Vasaskolan 1", "Aktiv", e=1, n=1),
        ]
    )
    crosswalk = lineage.build_lineage_crosswalk(schools)
    assert crosswalk.empty


def test_build_lineage_crosswalk_excludes_low_similarity_matches():
    """A single retiring unit sharing a site with a single, unrelated
    active unit is still 'mutual best' by construction (no other
    candidate to lose to) -- the `name_sim >= 0.8` floor is what actually
    rejects it, not the mutual-best ranking itself."""
    schools = pd.DataFrame(
        [
            _school("old1", "Komvux", "Vilande", e=1, n=1),
            _school("new1", "Henåns skola F-6", "Aktiv", e=1, n=1),
        ]
    )
    crosswalk = lineage.build_lineage_crosswalk(schools)
    assert crosswalk.empty


def test_build_lineage_crosswalk_drops_ambiguous_ties():
    """Two candidates equally close to one retiring unit's name (a school
    split into two identically-named `enhet`s) -- better to leave both
    unlinked than guess."""
    schools = pd.DataFrame(
        [
            _school("old1", "Hallernaskolan 7-9 enhet 2", "Vilande", e=1, n=1),
            _school("new1", "Hallernaskolan 7-9 enhet 1", "Aktiv", e=1, n=1),
            _school("new2", "Hallernaskolan 7-9 enhet 3", "Aktiv", e=1, n=1),
        ]
    )
    crosswalk = lineage.build_lineage_crosswalk(schools)
    assert crosswalk.empty


def test_load_lineage_crosswalk_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lineage, "schools_paths", lambda root=None: {"processed": tmp_path, "raw": tmp_path, "assembled": tmp_path}
    )
    with pytest.raises(FileNotFoundError):
        lineage.load_lineage_crosswalk()


def test_run_schools_lineage_saves_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lineage, "schools_paths", lambda root=None: {"processed": tmp_path, "raw": tmp_path, "assembled": tmp_path}
    )
    schools = pd.DataFrame(
        [
            _school("old1", "Älvegårdsskolan F-3", "Vilande", e=1, n=1),
            _school("new1", "Älvegårdsskolan 1-9", "Aktiv", e=1, n=1),
            _school("old2", "Vasaskolan 2", "Vilande", e=2, n=2),
            _school("new2", "Vasaskolan 1", "Aktiv", e=2, n=2),
        ]
    )
    schools.to_csv(tmp_path / "schools.csv", index=False)

    report = lineage.run_schools_lineage()
    assert report["n_schools"] == 4
    assert report["n_mixed_status_location_groups"] == 2
    assert report["n_lineage_links"] == 1  # only the genuine reorg, not the bare-digit twin

    saved = pd.read_csv(tmp_path / "skolenhetskod_lineage.csv", dtype={"old_code": str, "new_code": str})
    assert list(saved["old_code"]) == ["old1"]
