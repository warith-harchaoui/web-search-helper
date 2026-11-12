"""Read a corpus into passages.

A passage is the unit the engine ranks and returns an excerpt of. It carries
the text, the document and section it comes from (shown as the source), an
optional ``url`` the page can link to, and a free ``meta`` dict passed through
untouched to the browser.

Two inputs:

- **JSONL**, one passage per line: ``{"text": …, "doc": …, "section": …,
  "url": …, "meta": {…}}``. Use it when the passages are already cut, by
  your own pipeline.
- **A folder of Markdown or text files**: each ``#`` heading opens a section,
  the first heading (or the file name) titles the document, and paragraphs
  are grouped into passages of about ``target_words`` words.

>>> ps = passages_from_markdown("# Doc\\n\\n## Part\\n\\nOne two three.", "d.md")
>>> [(p.doc, p.section, p.text) for p in ps]
[('Doc', 'Part', 'One two three.')]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Passage:
    text: str
    doc: str = ""
    section: str = ""
    url: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"t": self.text, "c": self.doc, "s": self.section}
        if self.url:
            d["u"] = self.url
        if self.meta:
            d["m"] = self.meta
        return d


def read_jsonl(path: str | Path) -> list[Passage]:
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not isinstance(r.get("text"), str) or not r["text"].strip():
            raise ValueError(f"{path}:{n}: 'text' missing or empty")
        out.append(
            Passage(
                r["text"].strip(),
                str(r.get("doc", "")),
                str(r.get("section", "")),
                str(r.get("url", "")),
                dict(r.get("meta") or {}),
            )
        )
    return out


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def passages_from_markdown(source: str, name: str, target_words: int = 220) -> list[Passage]:
    """Cut one Markdown (or plain text) document into passages.

    Paragraphs are never split: a passage closes at the first paragraph
    boundary past ``target_words``, and never spans two sections.
    """
    doc = Path(name).stem
    section = ""
    out: list[Passage] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append(Passage("\n\n".join(buf), doc, section or doc))
            buf.clear()

    first_heading = True
    for block in re.split(r"\n\s*\n", source.replace("\r\n", "\n")):
        block = block.strip()
        if not block:
            continue
        m = _HEADING.match(block.splitlines()[0])
        if m:
            flush()
            title = m.group(2)
            if first_heading and len(m.group(1)) == 1:
                doc = title
            section = title
            first_heading = False
            rest = "\n".join(block.splitlines()[1:]).strip()
            if not rest:
                continue
            block = rest
        buf.append(" ".join(block.split()))
        if sum(len(b.split()) for b in buf) >= target_words:
            flush()
    flush()
    return out


def read_folder(folder: str | Path, target_words: int = 220) -> list[Passage]:
    """Every ``.md``, ``.markdown`` and ``.txt`` file under ``folder``, sorted by path."""
    folder = Path(folder)
    out: list[Passage] = []
    for f in sorted(folder.rglob("*")):
        if f.suffix.lower() in {".md", ".markdown", ".txt"} and f.is_file():
            out.extend(passages_from_markdown(f.read_text(encoding="utf-8"), f.name, target_words))
    return out


def read_corpus(path: str | Path, target_words: int = 220) -> list[Passage]:
    """A ``.jsonl`` file, a single Markdown/text file, or a folder of them."""
    path = Path(path)
    if path.is_dir():
        return read_folder(path, target_words)
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    return passages_from_markdown(path.read_text(encoding="utf-8"), path.name, target_words)
