#!/usr/bin/env python3
"""Measure each rung of the writer plan on a corpus's own questions.

best-engine-ai-helper ranks the browser models for the `rag-answer` usage by a
prior until a measurement exists; this script produces that measurement. It
serves a site (search.php + the index) with PHP, opens it in Chrome with WebGPU,
asks every question the corpus answers, and lets each model write its answer
from the excerpts the server returned. A written answer counts when it is
grounded (checkGrounding: every sentence supported by the excerpts it cites, at
least one citation) AND in the question's language. The score is the fraction
of answers that count, over all languages.

Only one variant per model is run (q4f16 where the GPU has shader-f16): q4 and
q4f16 are the same weights at two precisions, and the gap between them is not
what the ladder needs to learn.

Usage:
    python scripts/eval_writer.py SITE --questions fr=fr.inside --questions en=en.inside
        [--plan SITE/writer-plan.json] [--out scores.json] [--max-new-tokens 320]

SITE must hold search.php, web-search.js, search-data/<lang>.php (as written by
`web-search-helper install`). Needs php, playwright and Google Chrome.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

PAGE = """<!doctype html><meta charset="utf-8"><title>eval</title>
<script type="module">
import { WebSearch, Writer } from './web-search.js';
window.evalRung = async (rung, cases, maxNewTokens) => {
  const w = new Writer(rung);
  const t0 = performance.now();
  await w.load();
  const loadS = (performance.now() - t0) / 1000;
  const out = [];
  for (const c of cases) {
    const ws = new WebSearch({ endpoint: 'eval-search.php', lang: c.lang });
    const r = await ws.ask(c.q);
    if (!r.sure) { out.push({ ...c, sure: false }); continue; }
    const t1 = performance.now();
    let chars = 0;
    const a = await w.write(r, { question: c.q, lang: c.lang, maxNewTokens,
                                 onText: (t) => { chars = t.length; } });
    out.push({ ...c, sure: true, text: a.text, grounded: a.grounded, cited: a.cited,
               unsupported: a.unsupported, seconds: (performance.now() - t1) / 1000, chars });
  }
  return { loadS, out };
};
window.ready = true;
</script>"""

STOP = {
    "fr": {"le", "la", "les", "des", "est", "une", "dans", "qui", "que", "pour", "par", "sur", "et", "du"},
    "en": {"the", "is", "are", "of", "and", "that", "which", "for", "with", "this", "in", "to", "a"},
}


def language_of(text: str) -> str | None:
    words = [w.strip(".,;:!?()[]«»\"'’").lower() for w in text.split()]
    score = {lang: sum(w in s for w in words) for lang, s in STOP.items()}
    best = max(score, key=score.get)
    return best if score[best] > 0 else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("site", type=Path)
    ap.add_argument("--questions", action="append", required=True, help="LANG=FILE, one question per line")
    ap.add_argument("--plan", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("writer-scores.json"))
    ap.add_argument("--max-new-tokens", type=int, default=320)
    ap.add_argument("--port", type=int, default=8769)
    ap.add_argument("--profile", type=Path, default=Path(".chrome-eval-profile"))
    ap.add_argument(
        "--only", action="append", default=None, help="measure only models whose id contains this"
    )
    args = ap.parse_args()

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    plan = json.loads((args.plan or args.site / "writer-plan.json").read_text(encoding="utf-8"))
    cases = []
    for spec in args.questions:
        lang, path = spec.split("=", 1)
        cases += [
            {"lang": lang, "q": q.strip()}
            for q in Path(path).read_text(encoding="utf-8").splitlines()
            if q.strip() and not q.startswith("#")
        ]
    (args.site / "eval-writer.html").write_text(PAGE, encoding="utf-8")
    # The endpoint's quota (per address, per hour) would refuse a measurement
    # of several models; this wrapper gives every request a fresh quota state,
    # and exists only while the measurement runs.
    (args.site / "eval-search.php").write_text(
        "<?php define('WSH_STATE_DIR', sys_get_temp_dir() . '/wsh-eval-' . bin2hex(random_bytes(6)));\n"
        "require __DIR__ . '/search.php';\n",
        encoding="utf-8",
    )
    srv = subprocess.Popen(
        ["php", "-n", "-S", f"127.0.0.1:{args.port}", "-t", str(args.site)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    results = {"usage": plan["usage"], "date": time.strftime("%Y-%m-%d"), "models": {}}
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(args.profile), channel="chrome", headless=True, args=["--enable-unsafe-webgpu"]
            )

            # One fresh page per model: a page keeps its WebGPU and WASM memory
            # until it closes, and the third model of a run would not fit
            # beside the first two (std::bad_alloc, observed).
            def fresh_page():
                pg = ctx.new_page()
                pg.set_default_timeout(3_600_000)
                pg.goto(f"http://127.0.0.1:{args.port}/eval-writer.html")
                pg.wait_for_function("window.ready === true")
                return pg

            page = fresh_page()
            f16 = page.evaluate(
                "async () => { const a = await navigator.gpu.requestAdapter();"
                " return !!a && a.features.has('shader-f16'); }"
            )
            page.close()
            seen = set()
            for rung in plan["candidates"]:
                if rung["model"] in seen or (rung["needs_f16"] and not f16):
                    continue
                if args.only and not any(k in rung["model"] for k in args.only):
                    continue
                seen.add(rung["model"])
                print(f"{rung['model']} [{rung['dtype']}] ...", flush=True)
                page = fresh_page()
                try:
                    r = page.evaluate(
                        "([r, c, m]) => window.evalRung(r, c, m)", [rung, cases, args.max_new_tokens]
                    )
                except PlaywrightError as exc:  # a model that cannot load is a result too
                    results["models"][rung["model"]] = {
                        "dtype": rung["dtype"],
                        "score": None,
                        "error": str(exc).splitlines()[0],
                    }
                    print(f"  error: {str(exc).splitlines()[0]}", flush=True)
                    page.close()
                    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                    continue
                page.close()
                answered = [o for o in r["out"] if o["sure"]]
                for o in answered:
                    o["language_ok"] = language_of(o["text"]) == o["lang"]
                    o["counts"] = bool(o["grounded"] and o["language_ok"])
                by_lang = {}
                for lang in sorted({o["lang"] for o in answered}):
                    sub = [o for o in answered if o["lang"] == lang]
                    by_lang[lang] = round(sum(o["counts"] for o in sub) / len(sub), 3)
                score = round(sum(o["counts"] for o in answered) / len(answered), 3) if answered else None
                secs = [o["seconds"] for o in answered]
                results["models"][rung["model"]] = {
                    "dtype": rung["dtype"],
                    "score": score,
                    "by_language": by_lang,
                    "n": len(answered),
                    "load_s": round(r["loadS"], 1),
                    "median_answer_s": round(sorted(secs)[len(secs) // 2], 1) if secs else None,
                    "answers": answered,
                }
                print(f"  score {score} {by_lang}, n={len(answered)}, load {r['loadS']:.0f}s", flush=True)
                # Written after every model: a crash later loses nothing measured.
                args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            ctx.close()
    finally:
        srv.terminate()
        (args.site / "eval-writer.html").unlink(missing_ok=True)
        (args.site / "eval-search.php").unlink(missing_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
