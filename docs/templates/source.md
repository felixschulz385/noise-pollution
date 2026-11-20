---
type: source
state: current
updated: {{date}}
summary: "{{key}}: what the dataset is, in one line"
---

# {{title}}

**What it is.** Producer, version, resolution, coverage, licence.

**Config key:** `{{key}}`. **Module:** `src/data/sources/{{key}}.py`. **Steps:** FETCH, PREPARE.
**Requires:** —.

## Where it lands

- raw: `raw/<data_path>/…`
- prepared: `prepared/<data_path>/…`

## Columns

| Column | Meaning | Units |
|---|---|---|

## Caveats

Facts that only a real run can confirm are marked **needs live data**.
