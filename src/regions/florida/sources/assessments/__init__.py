"""FLDOE annual school-level assessment results.

Per-school-year workbooks (mean scale score and percent at each achievement
level, by school x grade x subject x subgroup) published on the FLDOE K-12
Student Assessment results pages. `www.fldoe.org` blocks automated clients, so
`fetch` is a manual-download orchestrator: it lays out the target folders,
optionally imports files you have already downloaded, and reports what is
present. Parsing / harmonisation is deliberately left to the notebook.
"""
