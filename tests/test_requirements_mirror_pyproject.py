"""One guard: requirements.txt must declare exactly what the package declares.

Two files state this package's runtime dependencies, and nothing else compares
them. Across the suite they drifted in ten of sixteen members at once
(2026-10-31): a dependency recorded in ``pyproject.toml`` and missing from
``requirements.txt`` builds, through ``pip install -r requirements.txt``, an
environment whose command line cannot start, while ``pip install -e .`` builds
a working one. Neither reader can notice, because a *missing* requirement
fails only when something imports it and a *surplus* one installs cleanly.

Here the risk is concrete: ``os-helper`` joined the core dependencies after
``requirements.txt`` was first written, exactly the move that drifted the rest
of the suite.

Deliberately regex, not ``tomllib``: this file must run on the floor Python
(3.10), where ``tomllib`` is not in the standard library, and ``[project]
dependencies`` is a flat array of strings that needs no TOML parser.

Author
------
Warith Harchaoui, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _declared() -> set[str]:
    """The ``[project] dependencies`` array of pyproject.toml, as written."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.DOTALL | re.MULTILINE)
    assert match, "pyproject.toml has no [project] dependencies array"
    # Comments inside the array may quote specifiers too, so they go before
    # anything is read as a dependency.
    body = re.sub(r"#[^\n]*", "", match.group(1))
    return {m.group(1) for m in re.finditer(r'"([^"]+)"', body)}


def _pinned() -> set[str]:
    """The dependency lines of requirements.txt, comments stripped."""
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {s for s in (line.split("#")[0].strip() for line in lines) if s}


def test_requirements_txt_mirrors_the_package_metadata() -> None:
    declared, pinned = _declared(), _pinned()
    assert pinned == declared, (
        f"requirements.txt only: {sorted(pinned - declared)}; pyproject.toml only: {sorted(declared - pinned)}"
    )
