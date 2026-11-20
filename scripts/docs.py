#!/usr/bin/env python3
"""Keep the documentation scaffold consistent: check, index, new.

    python scripts/docs.py check        # metadata, links, staleness, generated blocks
    python scripts/docs.py index        # rewrite every generated block in place
    python scripts/docs.py new line <slug> --title "..."
    python scripts/docs.py new prespec <line> <name>    # prespec-<name>.md, next step number
    python scripts/docs.py new note <line> <name>       # notes/<name>.md
    python scripts/docs.py new <kind> <line>            # any other template: results, outline, ...
    python scripts/docs.py new source <key>             # docs/data/<key>/README.md
    python scripts/docs.py new design <name>            # docs/design/YYYY-MM-<name>.md
    python scripts/docs.py --root <dir> check           # another repository

Configuration: ``docs/docs.toml`` (doc types, their states, extra files). The
conventions this enforces are in ``docs/conventions.md``. Standard library
only (Python >= 3.11 for ``tomllib``), so it runs in a git hook or in CI
without the project's environment.

**Metadata.** Every Markdown file under the docs root (except templates)
starts with a front-matter block::

    ---
    type: prespec              # a type from docs.toml
    state: recorded            # one of that type's states
    updated: 2026-11-16        # date of the last change of substance
    summary: "One line: what it is, or what came out"
    line: example              # required under docs/lines/<slug>/, equal to <slug>
    depends_on: [results.md]   # optional: paths relative to this file
    ---

Only flat ``key: value`` pairs and inline lists ``[a, b]`` are read.

**Generated blocks.** A Markdown file may hold blocks that ``index``
rewrites from the metadata::

    <!-- docs:begin lines -->            one row per line of work (its charter)
    <!-- docs:begin collect section=per-project-choices dir=. recursive -->
                                         the body of one named section from every doc
    <!-- docs:begin docs dir=lines/x --> one row per doc in a folder (relative to
                                         this file; options: ``recursive``, ``sort=path``,
                                         ``columns=summary,state`` (metadata keys);
                                         the default order is the type order in docs.toml,
                                         then ``step``, then path)
    <!-- docs:end -->

``check`` fails if a block is out of date, so status is never typed by hand.

**Checks.** Metadata present and valid; each line folder has a charter
(``README.md``) and its docs carry its slug; every relative Markdown link
in the docs root, the extra files and the notebooks' Markdown cells resolves; a doc is not older than a
doc it depends on (``depends_on``); generated blocks are current.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("scripts/docs.py needs Python >= 3.11 (tomllib)")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "docs" / "docs.toml"
REQUIRED = ("type", "state", "updated", "summary")
FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BLOCK_RE = re.compile(r"(<!-- docs:begin ([^>]*?) -->\n)(.*?)(<!-- docs:end -->)", re.S)
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


# -- model ------------------------------------------------------------------------------------

@dataclass
class Doc:
    path: Path                          # absolute
    meta: dict = field(default_factory=dict)
    title: str = ""
    body: str = ""

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("root", "docs")
    cfg.setdefault("lines", "docs/lines")
    cfg.setdefault("templates", "docs/templates")
    cfg.setdefault("extra", [])
    cfg.setdefault("exempt", [])
    cfg.setdefault("notebooks", [])
    return cfg


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        v = re.sub(r"\s+#.*$", "", v) if not v.strip().startswith(("\"", "'")) else v
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k.strip()] = [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
        else:
            meta[k.strip()] = _scalar(v)
    return meta, text[m.end():]


def read_doc(path: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    t = re.search(r"^# (.+)$", body, re.M)
    return Doc(path, meta, t.group(1).strip() if t else path.stem, body)


def tracked_md(cfg: dict) -> list[Path]:
    """Markdown files git tracks (or would: untracked but not ignored)."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / p for p in out if (ROOT / p).exists()]


def docs_under_root(cfg: dict) -> list[Doc]:
    root, tmpl = ROOT / cfg["root"], ROOT / cfg["templates"]
    exempt = {ROOT / e for e in cfg["exempt"]}
    return [read_doc(p) for p in tracked_md(cfg)
            if root in p.parents and tmpl not in p.parents and p not in exempt]


def line_of(path: Path, cfg: dict) -> str | None:
    lines = ROOT / cfg["lines"]
    if lines in path.parents:
        return path.relative_to(lines).parts[0]
    return None


# -- generated blocks -----------------------------------------------------------------------

def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _rel_link(src: Path, dst: Path) -> str:
    return Path(_relpath(dst, src.parent)).as_posix()


def _relpath(dst: Path, start: Path) -> str:
    import os
    return os.path.relpath(dst, start)


def render_lines(host: Path, docs: list[Doc], cfg: dict) -> str:
    lines_dir = ROOT / cfg["lines"]
    rows = [d for d in docs if d.meta.get("type") == "charter" and d.path.parent.parent == lines_dir]
    order = {s: i for i, s in enumerate(cfg["types"]["charter"]["states"])}
    rows.sort(key=lambda d: (order.get(d.meta.get("state"), 99), d.path.parent.name))
    out = ["| Line of work | State | Branch | Updated | Summary |", "|---|---|---|---|---|"]
    for d in rows:
        link = _rel_link(host, d.path.parent) + "/"
        out.append(f"| [{_cell(d.title)}]({link}) | {_cell(d.meta.get('state', ''))} | "
                   f"{_cell(d.meta.get('branch', '—'))} | {_cell(d.meta.get('updated', ''))} | "
                   f"{_cell(d.meta.get('summary', ''))} |")
    return "\n".join(out) + "\n"


def render_docs(host: Path, args: dict, docs: list[Doc], cfg: dict) -> str:
    folder = (host.parent / args.get("dir", ".")).resolve()
    recursive = "recursive" in args
    picked = []
    for d in docs:
        if d.path == host:
            continue
        if d.path.parent == folder or (recursive and folder in d.path.parents):
            picked.append(d)
    rank = {t: i for i, t in enumerate(cfg["types"])}   # docs.toml order is reading order
    if args.get("sort") == "path":
        picked.sort(key=lambda d: d.rel)
    else:
        picked.sort(key=lambda d: (rank.get(d.meta.get("type"), 99), _step(d), d.rel))
    cols = str(args.get("columns", "type,state,updated,summary")).split(",")
    out = ["| Doc | " + " | ".join(c.capitalize() for c in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for d in picked:
        name = d.path.parent.name if d.path.name == "README.md" else d.path.stem
        cells = []
        for c in cols:
            v = d.meta.get(c, "")
            if isinstance(v, list):
                v = ", ".join(v)
            if c == "state" and d.meta.get("note"):
                v = f"{v} ({d.meta['note']})"
            cells.append(_cell(v))
        out.append(f"| [{_cell(name)}]({_rel_link(host, d.path)}) | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def _step(d: Doc) -> float:
    try:
        return float(d.meta.get("step", ""))
    except ValueError:
        return float("inf")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def render_collect(host: Path, args: dict, docs: list[Doc], cfg: dict) -> str:
    """The body of one named section (``section=<slug of its heading>``) from every doc in a
    folder, under a link to its doc. Relative links are rewritten to work from the host."""
    folder = (host.parent / args.get("dir", ".")).resolve()
    recursive, want = "recursive" in args, args.get("section", "")
    rank = {t: i for i, t in enumerate(cfg["types"])}
    picked = [d for d in docs if d.path != host and
              (d.path.parent == folder or (recursive and folder in d.path.parents))]
    picked.sort(key=lambda d: (rank.get(d.meta.get("type"), 99), _step(d), d.rel))
    out = []
    for d in picked:
        parts = re.split(r"^(#{2,6} .+)$", d.body, flags=re.M)
        body = None
        for i in range(1, len(parts), 2):
            if _slug(parts[i].lstrip("#").strip()) == want:
                body = parts[i + 1].strip()
                break
        if not body or body.lower().startswith(("none", "—")):
            continue

        def relink(mm: re.Match) -> str:
            t = mm.group(1)
            if re.match(r"^[a-z][a-z0-9+.-]*:", t) or t.startswith(("#", "/")):
                return mm.group(0)
            path, _, anchor = t.partition("#")
            new = _rel_link(host, (d.path.parent / path).resolve()) + ("#" + anchor if anchor else "")
            return mm.group(0).replace(f"]({t})", f"]({new})")

        body = re.sub(r"\]\(([^)\s]+)\)", lambda mm: relink(mm), body)
        out.append(f"**[{d.title}]({_rel_link(host, d.path)})**\n\n{body}\n")
    return "\n".join(out) if out else "_None._\n"


def _block_args(spec: str) -> tuple[str, dict]:
    parts = spec.split()
    kind, args = parts[0], {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        args[k] = v or True
    return kind, args


def regenerate(path: Path, docs: list[Doc], cfg: dict) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")

    def sub(m: re.Match) -> str:
        kind, args = _block_args(m.group(2))
        if kind == "lines":
            body = render_lines(path, docs, cfg)
        elif kind == "docs":
            body = render_docs(path, args, docs, cfg)
        elif kind == "collect":
            body = render_collect(path, args, docs, cfg)
        else:
            raise ValueError(f"{path.relative_to(ROOT)}: unknown generated block '{kind}'")
        return m.group(1) + body + m.group(4)

    return text, BLOCK_RE.sub(sub, text)


def _checked_files(cfg: dict) -> list[Path]:
    """Markdown files under the docs root (templates excluded) plus the extra files."""
    root, tmpl = ROOT / cfg["root"], ROOT / cfg["templates"]
    files = [p for p in tracked_md(cfg) if root in p.parents and tmpl not in p.parents]
    return [p for p in dict.fromkeys(files + [ROOT / e for e in cfg["extra"]]) if p.exists()]


def block_hosts(cfg: dict) -> list[Path]:
    hosts = _checked_files(cfg)
    return [p for p in dict.fromkeys(hosts) if p.exists() and "<!-- docs:begin" in p.read_text(encoding="utf-8")]


# -- checks -----------------------------------------------------------------------------------

def check_meta(docs: list[Doc], cfg: dict) -> list[str]:
    errs = []
    types = cfg["types"]
    lines_dir = ROOT / cfg["lines"]
    for d in docs:
        m = d.meta
        if not m:
            errs.append(f"{d.rel}: no front matter")
            continue
        for k in REQUIRED:
            if not m.get(k):
                errs.append(f"{d.rel}: missing '{k}'")
        t = m.get("type")
        if t and t not in types:
            errs.append(f"{d.rel}: unknown type '{t}' (docs.toml: {', '.join(types)})")
        elif t and m.get("state") and m["state"] not in types[t]["states"]:
            errs.append(f"{d.rel}: state '{m['state']}' not allowed for {t} ({', '.join(types[t]['states'])})")
        if m.get("updated"):
            try:
                dt.date.fromisoformat(m["updated"])
            except ValueError:
                errs.append(f"{d.rel}: 'updated' is not YYYY-MM-DD")
        slug = line_of(d.path, cfg)
        if slug and m.get("line") != slug:
            errs.append(f"{d.rel}: 'line' must be '{slug}'")
        if t == "charter" and d.path.parent.parent != lines_dir:
            errs.append(f"{d.rel}: a charter is docs/lines/<slug>/README.md")
    if lines_dir.exists():
        for sub in sorted(p for p in lines_dir.iterdir() if p.is_dir()):
            ch = sub / "README.md"
            if not ch.exists() or read_doc(ch).meta.get("type") != "charter":
                errs.append(f"{sub.relative_to(ROOT)}: no charter (README.md with type: charter)")
    return errs


def check_links(cfg: dict) -> list[str]:
    errs = []
    for p in _checked_files(cfg):
        text = CODE_RE.sub("", p.read_text(encoding="utf-8"))
        for m in LINK_RE.finditer(text):
            target = m.group(1).split("#")[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
                continue
            if not (p.parent / target).exists():
                errs.append(f"{p.relative_to(ROOT)}: broken link '{m.group(1)}'")
    return errs


def check_notebook_links(cfg: dict) -> list[str]:
    """Relative links in the Markdown cells of tracked notebooks under ``notebooks``."""
    import json
    errs = []
    dirs = [ROOT / d for d in cfg["notebooks"]]
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.ipynb"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for rel in out:
        p = ROOT / rel
        if not p.exists() or not any(d in p.parents for d in dirs):
            continue
        try:
            cells = json.loads(p.read_text(encoding="utf-8")).get("cells", [])
        except json.JSONDecodeError:
            errs.append(f"{rel}: not valid JSON")
            continue
        for c in cells:
            if c.get("cell_type") != "markdown":
                continue
            text = CODE_RE.sub("", "".join(c.get("source", [])))
            for m in LINK_RE.finditer(text):
                target = m.group(1).split("#")[0]
                if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("/"):
                    continue
                if not (p.parent / target).exists():
                    errs.append(f"{rel}: broken link '{m.group(1)}'")
    return errs


def check_depends(docs: list[Doc]) -> list[str]:
    errs = []
    for d in docs:
        deps = d.meta.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            q = (d.path.parent / dep).resolve()
            if not q.exists():
                errs.append(f"{d.rel}: depends_on '{dep}' does not exist")
                continue
            u_dep, u_me = read_doc(q).meta.get("updated", ""), d.meta.get("updated", "")
            if u_dep and u_me and u_dep > u_me:
                errs.append(f"{d.rel}: stale — '{dep}' was updated {u_dep}, this doc {u_me}. "
                            f"Bring it in line, then bump 'updated'.")
    return errs


def cmd_check(cfg: dict) -> int:
    docs = docs_under_root(cfg)
    errs = check_meta(docs, cfg) + check_links(cfg) + check_notebook_links(cfg) + check_depends(docs)
    for h in block_hosts(cfg):
        try:
            old, new = regenerate(h, docs, cfg)
        except ValueError as e:
            errs.append(str(e))
            continue
        if old != new:
            errs.append(f"{h.relative_to(ROOT)}: generated block out of date (run: python scripts/docs.py index)")
    for e in errs:
        print(e)
    print(f"docs check: {len(docs)} docs, {len(errs)} problem(s)", file=sys.stderr)
    return 1 if errs else 0


def cmd_index(cfg: dict) -> int:
    docs = docs_under_root(cfg)
    n = 0
    for h in block_hosts(cfg):
        old, new = regenerate(h, docs, cfg)
        if old != new:
            h.write_text(new, encoding="utf-8")
            n += 1
            print(f"updated {h.relative_to(ROOT)}")
    print(f"docs index: {n} file(s) updated", file=sys.stderr)
    return 0


# -- new --------------------------------------------------------------------------------------

def _fill(template: Path, dest: Path, **kw) -> None:
    if dest.exists():
        sys.exit(f"{dest.relative_to(ROOT)} exists")
    text = template.read_text(encoding="utf-8")
    kw.setdefault("date", dt.date.today().isoformat())
    for k, v in kw.items():
        text = text.replace("{{" + k + "}}", str(v))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"created {dest.relative_to(ROOT)}")


def _next_step(folder: Path) -> int:
    steps = []
    for p in folder.glob("prespec-*.md"):
        try:
            steps.append(int(float(read_doc(p).meta.get("step", ""))))
        except ValueError:
            pass
    return max(steps, default=0) + 1


SPECIAL = {"line", "prespec", "note", "source", "design"}


def cmd_new(cfg: dict, a: argparse.Namespace) -> int:
    tmpl = ROOT / cfg["templates"]
    lines = ROOT / cfg["lines"]
    if a.kind not in SPECIAL and not (tmpl / f"{a.kind}.md").exists():
        kinds = sorted(SPECIAL | {p.stem for p in tmpl.glob("*.md")} - {"charter"})
        sys.exit(f"unknown kind '{a.kind}' (one of: {', '.join(kinds)})")
    if a.kind == "line":
        slug = _slug(a.name)
        _fill(tmpl / "charter.md", lines / slug / "README.md", line=slug, title=a.title or slug)
    elif a.kind == "source":
        _fill(tmpl / "source.md", ROOT / cfg["root"] / "data" / a.name / "README.md", key=a.name,
              title=a.title or a.name)
    elif a.kind == "design":
        # dated names: chronological, and two branches never collide on a number
        stamp = dt.date.today().strftime("%Y-%m")
        _fill(tmpl / "design.md", ROOT / cfg["root"] / "design" / f"{stamp}-{_slug(a.name)}.md",
              title=a.title or a.name)
    else:                                   # a doc inside a line
        if not (lines / a.name / "README.md").exists():
            sys.exit(f"no line '{a.name}' (python scripts/docs.py new line {a.name})")
        if a.kind in ("prespec", "note") and not a.extra:
            sys.exit(f"name the {a.kind}: python scripts/docs.py new {a.kind} {a.name} <name>")
        if a.kind == "prespec":
            step = _next_step(lines / a.name)
            _fill(tmpl / "prespec.md", lines / a.name / f"prespec-{_slug(a.extra)}.md", line=a.name,
                  step=step, title=a.title or a.extra)
        elif a.kind == "note":
            _fill(tmpl / "note.md", lines / a.name / "notes" / f"{_slug(a.extra)}.md", line=a.name,
                  title=a.title or a.extra)
        else:
            _fill(tmpl / f"{a.kind}.md", lines / a.name / f"{a.kind}.md", line=a.name,
                  title=a.title or a.name)
    print("then: fill it in, and run python scripts/docs.py index", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    global ROOT, CONFIG
    p = argparse.ArgumentParser(prog="python scripts/docs.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", help="repository root (default: the parent of scripts/)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="metadata, links, staleness, generated blocks")
    sub.add_parser("index", help="rewrite the generated blocks")
    n = sub.add_parser("new", help="a new doc from its template")
    n.add_argument("kind", help="line, prespec, note, source, design, or any template in docs/templates")
    n.add_argument("name", help="line slug, source key or design topic")
    n.add_argument("extra", nargs="?", help="prespec or note name")
    n.add_argument("--title")
    a = p.parse_args(argv)
    if a.root:
        ROOT = Path(a.root).resolve()
        CONFIG = ROOT / "docs" / "docs.toml"
    cfg = load_config()
    if a.cmd == "check":
        return cmd_check(cfg)
    if a.cmd == "index":
        return cmd_index(cfg)
    return cmd_new(cfg, a)


if __name__ == "__main__":
    sys.exit(main())
