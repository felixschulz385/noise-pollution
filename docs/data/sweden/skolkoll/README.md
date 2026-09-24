# `skolkoll`

A third-party aggregation of Skolverket's own `api.skolverket.se`
school-unit data (skolkoll.se), used narrowly for one purpose: recovering
real WGS84 coordinates for school units that have real SIRIS assessment
history (1998-2019, see `docs/data/sweden/assessments/README.md`) but no
longer exist anywhere in the live `Skolenhetsregistret` snapshot at all —
see `docs/data/sweden/schools/README.md`'s "Vanished pre-registry schools"
section for the full population this feeds and `panel/vanished_recovery.py`'s
module docstring for the recovery mechanics. This is **not** a general
school register for this project — `schools/` (the `Skolenhetsregistret`
fetch) remains the primary, authoritative identity/geocoding source for
every school still in the live register; `skolkoll` only covers the ones
that aren't.

`fetch`/`preprocess` are implemented and wired into
`panel/vanished_recovery.py`'s recovery stage.

## Why a third-party source, not another Skolverket API call

Skolverket's own live `Skolenhetsregistret` API (`schools/fetch.py`) is a
snapshot, not a panel — no history endpoint, no predecessor/successor
field (see `schools/lineage.py`'s module docstring for the same finding in
a different context). A purged `skolenhetskod` returns a 404 with
absolutely no trace it ever existed. Skolkoll retains exactly this
history: its own `status="UPPHORT"` (ceased) value — one of four it
carries (`AKTIV`/`VILANDE`/`UPPHORT`/`PLANERAD`, real counts 16,468 /
3,114 / 2,189 / 72) — never appears anywhere in our own registry fetch at
all, which only ever sees `Aktiv`/`Vilande`/`Planerad`.

## Format

Single flat-file CSV download, no authentication, no pagination:
`https://skolkoll.se/en/download/schools.csv` (~3.3MB, ~21,800 rows,
rebuilt daily on their end). UTF-8 with a BOM, `;`-delimited, a contiguous
leading block of `#`-prefixed metadata/variable-description lines before
the real header row (own `# Version:` line, read back by
`preprocess.py::extract_version` rather than tracked separately). Decimal
values use a **period**, not a comma — the opposite convention from this
repo's other Skolverket-derived source (SIRIS's archived exports use a
decimal comma, see `assessments/siris.py`).

**Columns** (renamed to this repo's existing Swedish-term names where a
direct `Skolenhetsregistret` analogue exists, so a future join against
`schools.geojson` reads the same way — see `preprocess.py::COLUMN_RENAME`):
`skolenhetskod` (Skolverket's own `api.skolverket.se` id — the modern
8-digit format — for `GR`/`GY`/`VUX`-type rows; preschool `FORSK` rows
carry a Skolkoll-synthetic `forsk-######` id instead, no real Skolverket
id exists for those, kept as-is not filtered), `namn`, `kommun_namn`,
`kommunkod`, `lan`, `huvudman_namn`, `skolformer`, `status` (Skolkoll's own
raw vocabulary, deliberately **not** recased to match the registry's
`Aktiv`/`Vilande`/`Planerad` — see `preprocess.py`'s docstring for why),
`wgs84_lat`/`wgs84_lng`, `total_pupils`, `pupils_per_teacher`,
`qualified_teachers_pct`, `merit_value_year9`,
`eligible_upper_secondary_pct`, `source`, `period`, `quality_class`
(A-E: verified/direct source/derived/estimated/unverified). The merit
value / teacher / pupil-count columns are carried through but not
currently used by anything in this pipeline — a possible future covariate
source, out of scope for what this module was built for.

## License

Per `https://skolkoll.se/en/data-licence/`: Skolverket's underlying data
carries "Skolverket open-data terms (no standard licence stated on the
verified page)" — described as "free use and reuse in your own services,
analyses and statistics", provided Skolverket is identified as the data
source (not implying its endorsement) and Skolkoll's own normalisation/
aggregation/selection is identified as Skolkoll processing, not
attributed to Skolverket. Both are done here: this README +
`preprocess.py`'s module docstring identify both sources plainly.

## How to get it

```
sweden data skolkoll fetch        # downloads schools.csv to raw/
sweden data skolkoll preprocess   # parses into skolkoll_schools.parquet
sweden data panel recover-vanished-schools   # the actual recovery + barrier match, see schools/README.md
```

No manual download step — unlike `traffic`/`road_network`/`noise_barriers`
(Lastkajen-gated), this is a public flat file, fetched the same way
`assessments/siris.py` fetches its own archived exports.

## Real numbers

`preprocess`: 21,843 rows, 19,724 geocoded (90.3%), 12,017 with a real
8-digit `skolenhetskod` (the rest are `FORSK` synthetic ids or blank).
Status: `AKTIV` 16,468 / `VILANDE` 3,114 / `UPPHORT` 2,189 / `PLANERAD` 72.

Cross-referenced against the 803 SIRIS-vanished codes (exact id match,
`panel/vanished_recovery.py::find_vanished_codes`): **306 (38%)** recover
a real coordinate, all `status=UPPHORT`, all among the 536 *modern*
8-digit vanished codes (0 of the 267 legacy 9-digit ones — see
`schools/README.md` for why). Full recovery + barrier-matching numbers in
that README's "Vanished pre-registry schools" section.
