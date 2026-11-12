"""Put the engine into a website folder, run it locally, check it online.

``install`` copies ``search.php``, ``web-search.js`` (and its ``.d.ts``) and the
index files into a site folder, under ``search-data/`` with a ``.htaccess``
that denies everything. The index files do not need it (requested by URL,
they answer 404), but two locks are better than one.

``check_online`` is to run AFTER uploading: it fetches the index files the way
a visitor would and fails if any byte of the corpus comes back; it then asks
the endpoint one question. An upload fails silently (a client that skips
dotfiles, a file left halfway); the page still displays.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

from .index import HEADER

ASSETS = ("search.php", "web-search.js", "web-search.d.ts")
DENY = """# web-search-helper: nothing in this folder is served.
# <FilesMatch> rather than a bare Require: a <FilesMatch> of a parent
# .htaccess (one that re-allows *.json, say) is merged AFTER directory
# rules and would win over them.
<FilesMatch ".*">
  Require all denied
</FilesMatch>
"""


def asset(name: str) -> Path:
    return Path(str(resources.files("web_search_helper") / "assets" / name))


def install(
    site: str | Path, indexes: list[str | Path], data_dir: str = "search-data", demo: bool = False
) -> list[Path]:
    """Copy the endpoint, the client and the index files into ``site``.

    ``demo`` also copies the bilingual demo page as ``demo.html``.
    """
    site = Path(site)
    site.mkdir(parents=True, exist_ok=True)
    written = []
    for name in ASSETS:
        written.append(Path(shutil.copy2(asset(name), site / name)))
    if demo:
        written.append(Path(shutil.copy2(asset("demo.html"), site / "demo.html")))
    data = site / data_dir
    data.mkdir(exist_ok=True)
    (data / ".htaccess").write_text(DENY, encoding="utf-8")
    written.append(data / ".htaccess")
    for ix in indexes:
        ix = Path(ix)
        with open(ix, "rb") as f:
            if f.read(len(HEADER)) != HEADER:
                raise ValueError(f"{ix} is not a web-search-helper index")
        dest = data / ix.name
        # Built straight into the site folder: already in place.
        if not (dest.exists() and dest.samefile(ix)):
            shutil.copy2(ix, dest)
        written.append(dest)
    if data_dir != "search-data":
        # search.php looks in ./search-data unless told otherwise.
        wrapper = site / "search.php"
        body = wrapper.read_text(encoding="utf-8")
        body = body.replace(
            "define('WSH_DATA_DIR', __DIR__ . '/search-data')",
            f"define('WSH_DATA_DIR', __DIR__ . '/{data_dir}')",
            1,
        )
        wrapper.write_text(body, encoding="utf-8")
    return written


def serve(site: str | Path, port: int = 8765, php: str = "php") -> subprocess.Popen:
    """``php -S`` on ``site``: the local twin of the hosting."""
    return subprocess.Popen(
        [php, "-S", f"127.0.0.1:{port}", "-t", str(site)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _get(url: str, data: bytes | None = None, timeout: float = 20):
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "web-search-helper-check"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check_online(
    base_url: str, langs: list[str], question: str = "test", data_dir: str = "search-data"
) -> dict:
    """Is the corpus private, and does the endpoint answer?"""
    base = base_url.rstrip("/") + "/"
    report: dict = {"leaks": [], "endpoint": {}}
    for lang in langs:
        for path in (f"{data_dir}/{lang}.php", f"{data_dir}/", f"{data_dir}/.htaccess"):
            status, body = _get(base + path)
            # Any non-empty 200 is a leak: the index answers an empty 404 and
            # the folder is denied.
            if status == 200 and body.strip():
                report["leaks"].append({"url": base + path, "bytes": len(body)})
        t0 = time.monotonic()
        status, body = _get(base + "search.php", json.dumps({"lang": lang, "q": question}).encode("utf-8"))
        report["endpoint"][lang] = {
            "status": status,
            "ms": round(1000 * (time.monotonic() - t0)),
            "body": body[:200].decode("utf-8", "replace"),
        }
    status, _ = _get(base + "search.php")
    report["get_refused"] = status == 405
    report["ok"] = (
        not report["leaks"]
        and report["get_refused"]
        and all(e["status"] == 200 for e in report["endpoint"].values())
    )
    return report


BENCH = r"""<?php
define('WSH_NO_MAIN', true);
require $argv[1];
$t0 = hrtime(true);
$I = wsh_load($argv[2]);
$t1 = hrtime(true);
$dim = $I['dim'];
mt_srand(1);
$times = [];
for ($r = 0; $r < (int)$argv[3]; $r++) {
    $v = []; $n = 0.0;
    for ($d = 0; $d < $dim; $d++) { $x = mt_rand() / mt_getrandmax() - 0.5; $v[] = $x; $n += $x * $x; }
    foreach ($v as $d => $x) $v[$d] = $x / sqrt($n);
    $a = hrtime(true);
    wsh_search($I, $argv[4], $v);
    $times[] = (hrtime(true) - $a) / 1e6;
}
sort($times);
echo json_encode(['load_ms' => ($t1 - $t0) / 1e6, 'search_ms_median' => $times[intdiv(count($times), 2)],
                  'search_ms_max' => end($times), 'vectors' => count($I['first']) ? array_sum(array_map('count', array_column($I['meta']['passages'], 'o'))) : 0,
                  'memory_mb' => memory_get_peak_usage() / 1e6,
                  'php' => PHP_VERSION,
                  'slowing_extensions' => array_values(array_filter(['pcov', 'xdebug', 'blackfire'], 'extension_loaded'))]);
"""


def bench(index: str | Path, runs: int = 5, question: str = "test question", php: str = "php") -> dict:
    """Time the PHP engine on an index: load, then full searches (words + meaning).

    The search is exhaustive (every window is compared with the question).
    ``ann-router`` would pick HNSW from 1 000 vectors under a 10 ms budget, but
    its thresholds are measured on numpy, not PHP, and the "I cannot answer"
    rule judges the ABSOLUTE best cosine, which an approximate index may miss.
    So the exhaustive scan stays as long as this measure fits the budget.
    """
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".php", delete=False) as f:
        f.write(BENCH)
        script = f.name
    try:
        out = subprocess.run(
            [
                php,
                "-d",
                "memory_limit=512M",
                script,
                str(asset("search.php")),
                str(index),
                str(runs),
                question,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        Path(script).unlink(missing_ok=True)
    return json.loads(out.stdout)
