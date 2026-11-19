# Noise pollution

Do noise barriers along roads and railways improve children's school achievement and later
outcomes? Noise is a widespread externality whose effect on human capital is far less studied
than that of air pollution or heat. Barriers are built at known dates on known stretches, which
makes their construction a staggered natural experiment: we study it at the school level in
Sweden and Florida, and for individual children on Swedish registers.

## Lines of work

Generated from each line's charter in [`docs/lines/`](docs/lines/):

<!-- docs:begin lines -->
| Line of work | State | Branch | Updated | Summary |
|---|---|---|---|---|
| [Florida: noise walls and school test scores](docs/lines/florida-schools/) | active | line/florida-schools | 2026-11-18 | Do FDOT noise walls raise test scores at the schools they protect? So far a clean null (CS ATT -0.051, RI p=0.456); post-wall cohorts at affluent-intake schools score lower |
| [Sweden: growing up behind a noise barrier](docs/lines/sweden-residents/) | active | line/sweden-residents | 2026-11-18 | Does growing up behind a noise barrier change children's school achievement and later outcomes? A cohort-exposure design on the 100 m grid and Swedish registers; design written, no estimate yet |
| [Sweden: noise barriers and school achievement](docs/lines/sweden-schools/) | active | line/sweden-schools | 2026-11-18 | Do Swedish road and rail noise barriers raise grade-9 achievement at the schools they protect? So far no effect beyond chance (RI p=0.186); a parental-education gradient survives |
<!-- docs:end -->

## Quick start

```bash
conda-lock install -n noise_pollution conda-lock.yml   # or: conda env create -f environment.yml
conda activate noise_pollution && pip install -e .
./.githooks/install.sh                             # notebooks, restricted data, docs
python scripts/docs.py check                       # documentation conventions
noise_pollution sweden data panel assemble         # one stage of one region's pipeline
```

Data lands under `data/` (git-ignored; `orchestration/configs/noise_pollution.yaml`). Credentials
for Trafikverket and Lastkajen go in `setup/secrets/` (git-ignored). The analysis notebooks
(`notebooks/<line>/`) need Stata with `csdid` and `reghdfe`, called through `pystata`.

Everything else is in [`docs/`](docs/README.md). This project was ported to
[research-project-template](https://github.com/felixschulz385/research-project-template) in
November 2026 ([`docs/design/2026-11-template-port.md`](docs/design/2026-11-template-port.md));
`copier update` brings in its later changes.

## License

Two licenses, by content type:

- **Source code** (`src/`, `scripts/`, configuration) — MIT, see [`LICENSE`](LICENSE).
- **Written research materials** (literature review, text, figures, tables under
  `output/documents/`) — Creative Commons Attribution 4.0 International (CC BY 4.0), see
  [`output/documents/LICENSE`](output/documents/LICENSE).

Input data under `data/` is third-party (Trafikverket, Skolverket, SCB, FDOT, FLDOE, NCES and
others) and is covered by neither license; it is subject to each provider's terms.
