---
type: index
state: current
updated: 2026-11-17
summary: "How the docs are organised: lines of work, doc types, metadata, generated indexes, the checker"
---

# Documentation Conventions

The docs are organised by **line of work**. Every doc has a **type**, and every doc **states its
own status** in a short metadata header. Indexes and status tables are **generated** from those
headers by [`scripts/docs.py`](../scripts/docs.py), so status is written once, in the doc it
belongs to. The checker runs in the pre-commit hook and in CI.

## Layout

```
docs/
  README.md            entry point; its tables are generated
  conventions.md       this page
  docs.toml            doc types and their states (read by scripts/docs.py)
  templates/           one template per doc type
  ideas.md             unscheduled ideas; each points to its line once started
  lines/<slug>/        one folder per line of work
    README.md          the charter: question, state, next step, branch (the only status)
    prespec-<name>.md  rules fixed before a step runs; its `step` field gives the order
    results.md         the record: every step's outcome
    outline.md         the story told from results.md (optional)
    literature.md      (optional)
    notes/             dated notes: checks, plans, data options, handoffs
  data/<key>/README.md one page per data source
  design/YYYY-MM-<topic>.md  infrastructure decisions, dated, never renamed
```

**A line of work** is one research question with its own life cycle: a project, a fork, a
successor. Its **slug** names everything that belongs to it: the folder
`docs/lines/<slug>/`, the branch `line/<slug>`, the notebooks `notebooks/<slug>/`, the figures
`output/figures/<slug>/` and the code `…/analysis/<slug>*.py`. Names never encode status or
order: a slug says what a line is, and order comes from metadata (`step`, dates), so no path
changes when a line closes or a step is inserted.

## Doc types

| Type | Where | Fixed sections | States |
|---|---|---|---|
| charter | `lines/<slug>/README.md` | question, why now, scope, state and next step, branch, generated list of documents | proposed → active → complete / stopped |
| prespec | `lines/<slug>/prespec-<name>.md` | decisions for the author, questions, data, specification, ◇ rules, outcomes, change log | draft → confirmed → run → recorded (or withdrawn) |
| results | `lines/<slug>/results.md` | summary, results step by step, what is supported, limitations, next steps, reproduction | current → final |
| outline | `lines/<slug>/outline.md` | story in one sentence, motivation, gap, design, findings as beats, discussion, limitations, figures, analysis key | current → final |
| literature | `lines/<slug>/literature.md` | the question in the literature, closest work, where the results sit, papers read | current → final |
| note | `lines/<slug>/notes/*.md` (or next to what it documents) | free, with a purpose line | current → record / superseded |
| source | `data/<key>/README.md` | what it is, where it lands, columns, caveats | current / superseded |
| design | `design/YYYY-MM-<topic>.md` | decision, reasoning, rejected alternatives, consequences | proposed → current / implemented → historical / superseded |
| index | navigation pages, this page, `ideas.md` | — | current |

These are the types of the **research** profile. The **software** profile replaces prespec,
results, outline and literature with `spec` (draft → agreed → implemented / dropped) and
`runbook` (current → superseded). The types, their states and their order (the reading order of
the generated tables) are set in `docs/docs.toml`; a project may add types there, with a
template of the same name in `docs/templates/`.

Start a doc from its template: `python scripts/docs.py new <kind> …` (see the script's help).
Pre-specs are named `prespec-<name>.md` and get the next `step` number; design records are named
`YYYY-MM-<topic>.md`. Older files with numbers in their names keep them.

## Metadata

Every Markdown file under `docs/` (except the templates) starts with:

```yaml
---
type: prespec
state: recorded
updated: 2026-11-17
line: example                # required under docs/lines/<slug>/
summary: "One line: what it is, or what came out"
step: 4                      # prespec: its step number (optional)
depends_on: [results.md]     # optional: docs this one is derived from
note: "…"                    # optional: a qualifier shown next to the state
branch: line/example         # charter: the line's branch
---
```

Only flat `key: value` pairs and inline lists are read.

## Where status lives

- **The status of a line:** its charter only (`state`, `summary`, the "State" paragraph).
- **The status of a doc:** its own metadata, and for a design record or a pre-spec also its
  banner under the title.
- **Results and verdicts:** the pre-spec's outcomes section and the line's `results.md`. A
  derived doc (`outline.md`) declares `depends_on: [results.md]`; the checker fails when the
  results page is newer, so both change in the same commit.
- **Everything else is generated:** the tables in `docs/README.md`, in each charter, in the
  root `README.md` and in the agent instructions (`AGENTS.md`). Never type a status into them;
  edit the doc's metadata and run `python scripts/docs.py index`.

Generated blocks look like this; `index` rewrites what is between the markers:

```markdown
<!-- docs:begin lines -->                    one row per line of work
<!-- docs:begin docs dir=lines/x recursive --> one row per doc in a folder (relative to the file;
                                               options: recursive, sort=path, columns=a,b)
<!-- docs:begin collect section=<heading-slug> dir=x recursive -->  one section from every doc
<!-- docs:end -->
```

## Pre-specification discipline

Every analysis block has rules (◇) written down before it runs. Change a rule only through the
change log at the end of the pre-spec, with a date and a reason, and never after seeing a result
the change could be fitted to. Checks that load no outcome (construction, coverage, counts) may
change construction rules; log them anyway. Implementation choices the pre-spec leaves open are
logged before the first fit.

## Design records

Named `YYYY-MM-<topic>.md`: chronological, and two branches never collide on a number. Code
cites them by path, so they are never renamed. When one goes out of date, set its `state` (and a
`note`) and add a dated banner under the title; the new decision gets a new record. Do not
rewrite what used to be true.

## The checker

`python scripts/docs.py check` fails on:

- missing or invalid metadata (unknown type, a state the type does not allow, a bad date, a
  missing `line`);
- a line folder without a charter;
- a broken relative link in `docs/`, in the extra files listed in `docs.toml`, or in the
  Markdown cells of the notebooks under the folders listed there;
- a doc older than a doc it depends on;
- a generated block that is out of date.

It needs only the Python standard library (3.11+). The pre-commit hook runs it; so does CI.
