"""scripts/docs.py on a throwaway repository: check, index, new, staleness, collect, --root.

Works with either documentation profile: the prespec test runs only when the project has a
prespec template.
"""
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]
TOOL = HERE / "scripts" / "docs.py"
CONFIG = HERE / "docs" / "docs.toml"
TEMPLATES = HERE / "docs" / "templates"
FM = "---\ntype: {t}\nstate: {s}\nupdated: {u}\nsummary: x\n{extra}---\n\n# {title}\n"


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(repo / "scripts" / "docs.py"), *args],
                          cwd=repo, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    shutil.copy(TOOL, tmp_path / "scripts" / "docs.py")
    (tmp_path / "docs").mkdir()
    cfg = re.sub(r"extra = \[.*?\]\n", 'extra = ["README.md"]\n', CONFIG.read_text(), flags=re.S)
    cfg = re.sub(r"notebooks = \[.*?\]\n", "notebooks = []\n", cfg, flags=re.S)
    (tmp_path / "docs" / "docs.toml").write_text(cfg)
    shutil.copytree(TEMPLATES, tmp_path / "docs" / "templates")
    (tmp_path / "README.md").write_text("# X\n\n<!-- docs:begin lines -->\n<!-- docs:end -->\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_new_line_index_check(repo: Path):
    assert _run(repo, "new", "line", "demo", "--title", "Demo line").returncode == 0
    assert _run(repo, "new", "note", "demo", "first check").returncode == 0
    r = _run(repo, "check")
    assert r.returncode == 1 and "generated block out of date" in r.stdout
    assert _run(repo, "index").returncode == 0
    r = _run(repo, "check")
    assert r.returncode == 0, r.stdout
    assert "[Demo line](docs/lines/demo/)" in (repo / "README.md").read_text()
    assert "(notes/first-check.md)" in (repo / "docs/lines/demo/README.md").read_text()


@pytest.mark.skipif(not (TEMPLATES / "prespec.md").exists(), reason="no prespec template")
def test_prespec_steps_order_the_table(repo: Path):
    _run(repo, "new", "line", "demo")
    assert _run(repo, "new", "prespec", "demo", "zeta step").returncode == 0
    assert _run(repo, "new", "prespec", "demo", "alpha step").returncode == 0
    assert "step: 2" in (repo / "docs/lines/demo/prespec-alpha-step.md").read_text()
    _run(repo, "index")
    charter = (repo / "docs/lines/demo/README.md").read_text()
    assert charter.index("prespec-zeta-step") < charter.index("prespec-alpha-step")   # by step


def test_check_catches_problems(repo: Path):
    _run(repo, "new", "line", "demo")
    notes = repo / "docs/lines/demo/notes"
    notes.mkdir(parents=True)
    extra = "line: demo\n"
    (notes / "base.md").write_text(FM.format(t="note", s="current", u="2999-01-01", extra=extra,
                                             title="Base") + "\n[gone](nowhere.md)\n")
    (notes / "derived.md").write_text(FM.format(t="note", s="current", u="2026-01-01",
                                                extra=extra + "depends_on: [base.md]\n", title="D"))
    ch = repo / "docs/lines/demo/README.md"
    ch.write_text(ch.read_text().replace("state: proposed", "state: finished"))
    (repo / "docs/lines/orphan").mkdir()
    (repo / "docs/lines/orphan/x.md").write_text("# no front matter\n")
    out = _run(repo, "check").stdout
    assert "derived.md: stale" in out
    assert "broken link 'nowhere.md'" in out
    assert "state 'finished' not allowed for charter" in out
    assert "docs/lines/orphan: no charter" in out
    assert "orphan/x.md: no front matter" in out


def test_design_names_collect_and_root(repo: Path, tmp_path_factory):
    assert _run(repo, "new", "design", "storage layout").returncode == 0
    stamp = dt.date.today().strftime("%Y-%m")
    rec = repo / f"docs/design/{stamp}-storage-layout.md"
    assert rec.exists()
    rec.write_text(rec.read_text() + "\n## Per-project choices\n\n- pick a [format](../other.md)\n")
    (repo / "docs/other.md").write_text(FM.format(t="index", s="current", u="2026-01-01", extra="",
                                                  title="Other"))
    (repo / "docs/choices.md").write_text(
        FM.format(t="index", s="current", u="2026-01-01", extra="", title="Choices")
        + "\n<!-- docs:begin collect section=per-project-choices dir=design -->\n<!-- docs:end -->\n")
    _run(repo, "index")
    text = (repo / "docs/choices.md").read_text()
    assert "- pick a [format](other.md)" in text and f"design/{stamp}-storage-layout.md" in text
    other = tmp_path_factory.mktemp("elsewhere")
    r = subprocess.run([sys.executable, str(repo / "scripts/docs.py"), "--root", str(repo), "check"],
                       cwd=other, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
