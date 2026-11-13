#!/usr/bin/env python3
"""Regenerate the writer plan and the parity fixture from best-engine-ai-helper.

The model ladder is best-engine's decision, not this package's: run this after
best-engine's browser catalog changes (new model, new measurement), with
best-engine-ai-helper importable. Writes:

- src/web_search_helper/assets/writer-plan.json, the ladder the page walks;
- tests/js/choose-fixture.json, best-engine's `browser.choose` on a grid of
  simulated devices, which the JavaScript `chooseRung` must reproduce.
"""

import itertools
import json
from pathlib import Path

from best_engine_ai_helper import browser

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "src/web_search_helper/assets/writer-plan.json"
FIXTURE = ROOT / "tests/js/choose-fixture.json"


def main() -> None:
    plan = browser.plan("rag-answer", languages=["fr", "en"])
    PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cached_rung = f"{plan['candidates'][-1]['model']}|{plan['candidates'][-1]['dtype']}"
    scenarios = []
    for webgpu, f16, mobile, save, mem, free, bw, cached in itertools.product(
        [True, False],
        [True, False],
        [False, True],
        [False, True],
        [None, 2, 4, 8, 32],
        [None, 1e9, 3e9, 4e9, 1e11],
        [None, 1e6, 5e6, 2e7, 6e7],
        [[], [cached_rung]],
    ):
        if not webgpu and (f16 or mobile or save):
            continue
        device = {
            "webgpu": webgpu,
            "f16": f16,
            "mobile": mobile,
            "save_data": save,
            "device_memory_gb": mem,
            "storage_free_bytes": free,
            "bandwidth_Bps": bw,
            "cached": cached,
        }
        r = browser.choose(plan, device)
        rung = f"{r['candidate']['model']}|{r['candidate']['dtype']}" if r["candidate"] else None
        scenarios.append(
            {"device": device, "expected": {"rung": rung, "reason": r["reason"], "seconds": r["seconds"]}}
        )
    scenarios.append(
        {
            "device": {"webgpu": True, "f16": True, "effective_type": "3g", "bandwidth_Bps": 6e7},
            "expected": {"rung": None, "reason": "network", "seconds": None},
        }
    )
    FIXTURE.write_text(
        json.dumps({"generated_by": "best_engine_ai_helper.browser.choose", "scenarios": scenarios}, indent=0)
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(plan['candidates'])} rungs -> {PLAN.relative_to(ROOT)}; "
        f"{len(scenarios)} scenarios -> {FIXTURE.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
