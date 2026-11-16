"""
Every console script answers ``--help`` and returns, instead of serving.

Until 0.2.0, ``web-search-helper-api`` and ``web-search-helper-mcp`` read
their port from ``PORT`` and ignored their arguments, so
``web-search-helper-api --help`` started a server on port 8040 and never
returned (audio-helper's MCP door had the same defect). Each script named in
``[project.scripts]`` now runs with ``--help`` under a timeout and must print
a click usage line.

The scripts are imported from the source tree (``PYTHONPATH`` follows the
test process), so the check judges this checkout rather than whatever version
is installed.

Author
------
Warith HARCHAOUI <warithmetics@deraison.ai>
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _scripts() -> list[tuple[str, str, str]]:
    """``(name, module, function)`` for each console script, read from pyproject.toml."""
    # Read rather than parsed: ``tomllib`` is 3.11+.
    manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = manifest.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    return re.findall(r'^([\w-]+)\s*=\s*"([\w.]+):(\w+)"', block, re.M)


def test_the_scripts_are_found() -> None:
    # An empty parametrisation would pass silently.
    assert {s[0] for s in _scripts()} == {
        "web-search-helper",
        "web-search-helper-api",
        "web-search-helper-mcp",
    }


@pytest.mark.parametrize(("name", "module", "func"), _scripts())
def test_the_command_answers_help(name: str, module: str, func: str) -> None:
    # The API and MCP doors need their extras; without them there is nothing
    # to start, hence nothing to hang.
    if name.endswith("-api"):
        pytest.importorskip("fastapi")
    if name.endswith("-mcp"):
        pytest.importorskip("fastapi_mcp")
    code = f"import sys; from {module} import {func}; sys.argv[0] = {name!r}; {func}()"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])}
    proc = subprocess.run(
        [sys.executable, "-c", code, "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "Usage:" in proc.stdout, proc.stdout[:400]
