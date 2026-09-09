"""Test suite configuration.

`__init__.py` convention: there are NO `__init__.py` files anywhere in
`tests/`. Pytest imports each test file by its (unique) basename, so adding a
test directory needs no bookkeeping. The cost is that every test file's
basename must stay unique across the whole tree.

Running the suite: run `pytest` from the repository root so that
`from src.… import …` imports resolve. There is no `pytest.ini` /
`[tool.pytest.ini_options]` section — rootdir detection is left to pytest's
defaults.

`tests/` mirrors `src/` 1:1: a module at `src/x/y.py` has its tests under
`tests/x/`.
"""
