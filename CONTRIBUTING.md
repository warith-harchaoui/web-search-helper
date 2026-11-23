# Contributing

Thanks for your interest. This file documents how the project is
maintained and what to expect.

## Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Given a version `MAJOR.MINOR.PATCH`:

- **MAJOR** bumps when the public API changes in a way that breaks
  existing callers: function removed, signature changed in an
  incompatible way, exception type changed, return shape changed,
  default behavior reversed.
- **MINOR** bumps when functionality is added in a backwards-compatible
  way: new function, new optional parameter, new optional dependency.
- **PATCH** bumps for backwards-compatible fixes only: bug fixes,
  internal refactors, packaging fixes, dependency-pin bumps that
  don't change observable behavior.

### What counts as a breaking change

Counts as breaking (MAJOR bump):

- Removing or renaming a public function / class / attribute.
- Changing a function's positional argument order or making an
  optional argument required.
- Changing the return type, shape, or semantics of a public function.
- Changing the exception class raised for a known error path (e.g.
  going from `ValueError` to `RuntimeError`).
- Removing a public submodule.
- Tightening the supported Python version range.
- Changing the index file format so that a `search.php` already deployed
  can no longer read a new index, or the reverse (the `WSH1` magic and the
  `format` field in the metadata exist for this).
- Changing the JSON protocol between `web-search.js` and `search.php`
  (`{lang, q, v?}` in, `{sure, terms, hits?}` out) incompatibly.

Does not count as breaking (MINOR / PATCH):

- Adding a new optional argument with a backwards-compatible default.
- Adding a new function or submodule.
- Tightening dependency pins to a newer minor version (assuming the
  new dep is still compatible).
- Loosening dependency pins.
- Internal refactors that preserve observable behavior.
- Type-annotation precision improvements.
- Docstring and README changes.

### Anything underscore-prefixed is private

Names starting with `_` are not part of the public API and may change
between any two releases without a major bump. Don't rely on them in
external code.

## Layout

The package uses the src layout: the code lives in `src/web_search_helper/`,
and the files shipped to a website (`search.php`, `web-search.js`,
`web-search.d.ts`, `writer-plan.json`, `demo.html`) in
`src/web_search_helper/assets/`. Tests are in `tests/`; the JavaScript tests
of the client are in `tests/js/`.

## The parity rule: `engine.py` ⇔ `search.php`

`engine.py` is the reference twin of `search.php`. Any change to the ranking,
the verdict, the excerpts or the tokenizer is made in **both** files, in the
same commit. `tests/test_php_parity.py` runs both engines on the same
questions, in French and in English, and fails when they disagree; it needs
`php` (>= 7.4, with mbstring) on the PATH. The same goes for the browser side:
`chooseRung` in `web-search.js` is checked against best-engine-ai-helper's
Python `browser.choose` (`tests/test_writer.py`, needs `node`).

## Coding style

Every Python file in this suite follows the same shape (mandate 2026-06-29;
the full standard is [`CODING.md`](CODING.md)):

1. **Numpy-style docstring on every function and class.** Sections in order:
   short summary, optional extended summary, `Parameters`, `Returns` /
   `Yields`, `Raises`, `Examples`, `Notes`. Sphinx-friendly underlines
   (`----`).
2. **Module-level header docstring on every `.py` file.** Numpy style, with
   a `Module summary` paragraph, a `Usage example` section, and an
   `Author` section pointing at
   [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).
3. **Full type annotations.** Parameters, returns, class attributes,
   module-level constants. `from __future__ import annotations` to keep
   forward refs cheap. Prefer `TypedDict` for structured returns
   (already a pattern across the suite).
4. **Generous comments.** Explain the *why* and any non-obvious *how*.
   Comments above blocks, not redundant inline. Cite the trade-off when
   picking an algorithm or backend.
5. **No bare `print(...)` in `.py` code.** Each module that logs declares
   `logger = logging.getLogger(__name__)` at the top and calls `logger.info(...)`;
   the entry point alone configures logging (`osh.init_logging(...)`), and
   `osh.verbosity(level)` tunes it. **Docs (README, LISEZMOI,
   EXAMPLES.md, docstring examples) keep `print(...)`**: tutorial code reads
   naturally that way.
6. **`print(...)` in docs is followed by a `#`-comment showing expected
   output.** Doctest / REPL style, either trailing inline
   (`print(x)  # 42`) or on the next line (`# 42`).
7. **EXAMPLES.md** at the repo root, linked from README + LISEZMOI. Self-
   contained, runnable cookbook of the helper's main use cases.
8. **Wherever `brew install <pkg>` appears in the docs**, the line is
   accompanied by `(install `brew` thanks to [brew.sh](https://brew.sh/))`
   when not already obvious from context.

web-search-helper loads no credentials, so it ships no
`settings.yaml.example`.

## Releases

Releases live in [`CHANGELOG.md`](CHANGELOG.md) following the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Each
release is tagged `vX.Y.Z` in git and published as a GitHub release.

Cross-helper dependencies (e.g. `os-helper>=4.2,<5`) are version
ranges against the PyPI releases, not git tag pins.

## CI

GitHub Actions runs `pytest` on Python 3.10 and 3.13 (Linux), the two ends
of the supported range, with the core install plus the `dev`, `api` and `mcp`
extras: the hash embedder, no model download. The runner's PHP is checked
first, so the parity test between `search.php` and `engine.py` runs on every
push. A separate `ruff` job (pinned to 0.15.21) blocks merging on both lint
and format violations. The heavy sweep, the real embedder included, runs
locally pre-push.

## Running tests locally

```bash
pip install -e ".[embed,api,mcp,dev]"
python -m pytest -q          # needs php on the PATH for the parity tests
python -m pytest -q -m ""    # the same sweep as the pre-push gate
```

Tests skip, rather than fail, when `php`, `node`, `fastapi`, `fastapi_mcp`
or `best_engine_ai_helper` is missing; the pre-push gate is only meaningful
on a machine that has them all.

## Pre-push hook

A git `pre-push` hook blocks the push outright if `ruff check`, `ruff
format --check`, or the full `pytest -q -m ""` sweep fails: a red local
state never reaches CI. One-time setup per clone:

```bash
git config core.hooksPath .githooks
```

Bypass only when you really mean it: `git push --no-verify`.

## Authorship

Sole author: [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).
External contributions are welcome: please open an issue or PR.

Special thanks to [Mohamed Chelali](https://mchelali.github.io) and
[Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug) for fruitful
discussions throughout the suite's evolution.

## License

[BSD-3-Clause](LICENSE), same as scikit-learn / numpy / scipy.
