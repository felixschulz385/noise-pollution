"""`find_repo_root` must not require `data/` to exist -- it's gitignored and
legitimately absent on a fresh checkout (e.g. CI), and `region_dirs` relies on
`find_repo_root` succeeding so it can create `data/` in the first place."""
from src.core.pipeline.layout import find_repo_root


def test_find_repo_root_does_not_require_data_dir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "src" / "regions" / "sweden"
    nested.mkdir(parents=True)

    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_finds_root_from_a_parent_directory(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("")

    assert find_repo_root(tmp_path) == tmp_path.resolve()
