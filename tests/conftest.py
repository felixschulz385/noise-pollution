"""Root conftest.

Convention: no ``__init__.py`` anywhere in ``tests/``; pytest imports each test file by its
basename, so basenames must be unique across the tree (region test files that would collide
carry the region, e.g. ``test_sweden_panel_assemble.py``). Test files never import each other or
a ``conftest.py``; shared setup is a fixture (a helper function is a fixture that returns it).
Run ``pytest`` from the repository root with the package installed (``pip install -e .``).

``tests/`` mirrors ``src/noise_pollution/``: a module at ``src/noise_pollution/x/y.py`` has its
tests under ``tests/x/``; tools under ``scripts/`` are tested under ``tests/scripts/``.
"""
