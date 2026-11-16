# web-search-helper as an agent skill

`skills/web-search-helper/` packages `web-search-helper` as a **Claude Skill**
*and* an **OpenCode skill**: both ecosystems read the same `SKILL.md` (YAML
frontmatter + Markdown body + progressive-disclosure `references/`).
Installing it lets an agent discover web-search-helper and add a private
search to a website on the user's behalf: index the corpus, calibrate the
refusal, install the PHP endpoint, check after upload that nothing leaks.

## Layout

```
skills/web-search-helper/
├── SKILL.md                  # name + trigger-rich description + instructions
└── references/
    ├── cli-reference.md      # full subcommand + flag matrix
    ├── surfaces.md           # library, CLI, the website files, HTTP API, MCP, /gui
    └── triggers.md           # exhaustive, auditable trigger catalogue
```

Progressive disclosure, as the published skill standard prescribes: the YAML
frontmatter is always in the host model's context, `SKILL.md`'s body loads only
when the skill looks relevant, and `references/*.md` load only when a task
actually needs that depth. The `description` stays under the 1024-character cap;
the exhaustive trigger list lives in `references/triggers.md`.

## Install for Claude Code / Claude Desktop

Skills live under `~/.claude/skills/` (user) or `.claude/skills/` (project). To
track this repo's copy rather than duplicate it, symlink it:

```bash
ln -sfn "$PWD/skills/web-search-helper" ~/.claude/skills/web-search-helper
# per-project instead:
mkdir -p /path/to/project/.claude/skills
ln -sfn "$PWD/skills/web-search-helper" /path/to/project/.claude/skills/web-search-helper
```

## Install for OpenCode

OpenCode reads skills from `~/.opencode/skills/` (or `~/.config/opencode/skills/`):

```bash
mkdir -p ~/.opencode/skills
ln -sfn "$PWD/skills/web-search-helper" ~/.opencode/skills/web-search-helper
```

## Keeping triggers enforced

The host model only sees `SKILL.md`'s `description` before deciding to load the
skill, so every real trigger must be represented there, compressed into the
1024-character budget. `scripts/check_triggers.py` checks that every
capability bucket is named, that a SKIP clause is present and that the budget
holds; `tests/test_skill.py` runs it. `references/triggers.md` is the
human-reviewable superset, and it mirrors the repo-root `TRIGGERS.md` (the
user-facing catalogue). When one changes, change the other.

No secrets live in this skill. Indexing runs on the user's machine; the corpus
never leaves it except as the index file uploaded to their own host. The
network calls are the one-time download of the embedding model (by
sentence-transformers here, by transformers.js in the visitor's browser) and,
when the written answer is enabled, the model of the plan, fetched by the
visitor's browser.
