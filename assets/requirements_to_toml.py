"""
requirements_to_toml: one-shot helper that converts a ``requirements.txt``
into the ``[tool.poetry.dependencies]`` block of a Poetry ``pyproject.toml``.

Module summary
--------------
Kept in ``assets/`` because it is a build-time utility, not part of the
``web_search_helper`` public API, and because ``assets/manual_poetry.sh``
calls it. The project itself builds with setuptools from ``pyproject.toml``;
this script only serves someone who wants a Poetry twin of the same
dependencies.

Usage example
-------------
>>> #   python assets/requirements_to_toml.py \\
>>> #       --requirements_file requirements.txt \\
>>> #       --project_name web-search-helper \\
>>> #       --description "Web Search Helper" \\
>>> #       --authors "Warith Harchaoui <warithmetics@deraison.ai>" \\
>>> #       --python_version "^3.10" --opensource

Author
------
Warith Harchaoui, Ph.D., https://linkedin.com/in/warith-harchaoui/
"""

from __future__ import annotations

import os

import click


def read_requirements(file_path: str = "requirements.txt") -> list[str]:
    """Return the requirement lines of ``file_path``, comments and blanks dropped.

    Parameters
    ----------
    file_path : str
        Path of the pip requirements file.

    Returns
    -------
    list of str
        One specifier per entry, inline comments removed.
    """
    with open(file_path, encoding="utf-8") as f:
        # An inline comment ("click>=8.1  # why") is not part of the specifier.
        lines = [line.split("#", 1)[0].strip() for line in f]
    return [line for line in lines if line]


def format_dependencies(requirements: list[str]) -> str:
    """Render pip specifiers as Poetry ``name = "constraint"`` lines.

    Parameters
    ----------
    requirements : list of str
        Specifiers such as ``numpy>=1.24`` or ``os-helper>=4.2,<5``.

    Returns
    -------
    str
        One indented TOML line per requirement.

    Examples
    --------
    >>> format_dependencies(["numpy>=1.24", "click"])
    '    numpy = ">=1.24"\\n    click = "*"\\n'
    """
    lines = []
    for requirement in requirements:
        # A git URL becomes a Poetry git dependency on main.
        if "@ git+" in requirement:
            package, url = requirement.split("@ git+", 1)
            url = url.replace("git@github.com:", "https://github.com/").split("@")[0].strip()
            lines.append(f'    {package.strip()} = {{ git = "{url}", branch = "main" }}\n')
            continue
        # Otherwise split at the first comparison operator: the name is what
        # precedes it, the whole constraint (ranges included) what follows.
        for i, ch in enumerate(requirement):
            if ch in "<>=!~":
                name, constraint = requirement[:i].strip(), requirement[i:].strip()
                lines.append(f'    {name} = "{constraint}"\n')
                break
        else:
            # No operator: any version.
            lines.append(f'    {requirement.strip()} = "*"\n')
    return "".join(lines)


def generate_pyproject_toml(
    requirements: list[str],
    project_name: str,
    description: str,
    authors: list[str],
    python_version: str,
    opensource: bool = False,
) -> str:
    """Return the text of a Poetry ``pyproject.toml``.

    Parameters
    ----------
    requirements : list of str
        Pip specifiers, as read by :func:`read_requirements`.
    project_name, description : str
        Package metadata.
    authors : list of str
        ``"Name <email>"`` entries.
    python_version : str
        Poetry constraint on Python, e.g. ``^3.10``.
    opensource : bool
        When True, declare the suite's licence, BSD-3-Clause.

    Returns
    -------
    str
        The TOML document.
    """
    licence = "BSD-3-Clause" if opensource else ""
    return f"""
[tool.poetry]
name = "{project_name}"
version = "1.0.0"
description = "{description}"
authors = {authors}
license = "{licence}"
readme = "README.md"

[tool.poetry.dependencies]
python = "{python_version}"
{format_dependencies(requirements)}
[tool.poetry.dev-dependencies]
pytest = ">=7"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
"""


def write_pyproject_toml(content: str, file_path: str = "pyproject.toml") -> None:
    """Write ``content`` to ``file_path`` (UTF-8)."""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--project_name", default="my_project", show_default=True, help="The name of your project")
@click.option(
    "--description",
    default="A sample Python project",
    show_default=True,
    help="A description of your project",
)
@click.option(
    "--authors", default="Your Name <you@example.com>", show_default=True, help="Comma-separated authors"
)
@click.option(
    "--python_version", default="^3.10", show_default=True, help="Python constraint for the project"
)
@click.option(
    "--requirements_file", default="requirements.txt", show_default=True, help="Path to requirements.txt"
)
@click.option(
    "--output_file", default="pyproject.toml", show_default=True, help="Path of the pyproject.toml to write"
)
@click.option("--opensource", is_flag=True, help="Declare the BSD-3-Clause licence")
def main(
    project_name: str,
    description: str,
    authors: str,
    python_version: str,
    requirements_file: str,
    output_file: str,
    opensource: bool,
) -> None:
    """Generate a Poetry pyproject.toml from requirements.txt."""
    author_list = [a.strip() for a in authors.split(",") if a.strip()]
    # Poetry reads a bare version as exact; a caret keeps the usual meaning.
    if not python_version.startswith("^"):
        python_version = f"^{python_version}"
    if not os.path.exists(requirements_file):
        raise click.ClickException(f"{requirements_file} not found.")
    toml_content = generate_pyproject_toml(
        read_requirements(requirements_file),
        project_name=project_name,
        description=description,
        authors=author_list,
        python_version=python_version,
        opensource=opensource,
    )
    write_pyproject_toml(toml_content, file_path=output_file)
    click.echo(f"pyproject.toml has been generated at {output_file}.")


if __name__ == "__main__":
    main()
