// Node tests for the browser client's pure parts: the writer's variant
// choice and the grounding check. Run: node --test tests/js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chooseRung, probeDevice, measureBandwidth, checkGrounding, splitSentences } from '../../src/web_search_helper/assets/web-search.js';

const here = new URL('.', import.meta.url);
const plan = JSON.parse(readFileSync(new URL('../../src/web_search_helper/assets/writer-plan.json', here)));
const fixture = JSON.parse(readFileSync(new URL('choose-fixture.json', here)));

test('chooseRung agrees with best-engine on every fixture scenario', () => {
  // The fixture was computed by best_engine_ai_helper.browser.choose on the same
  // plan; tests/test_writer_parity.py regenerates it when best-engine is there.
  assert.ok(fixture.scenarios.length > 1000);
  for (const { device, expected } of fixture.scenarios) {
    const r = chooseRung(plan, device);
    const rung = r.candidate ? `${r.candidate.model}|${r.candidate.dtype}` : null;
    assert.deepEqual({ rung, reason: r.reason, seconds: r.seconds }, expected, JSON.stringify(device));
  }
});

const adapter = (f16) => ({ features: new Set(f16 ? ['shader-f16'] : []) });

test('probeDevice reads what the browser exposes, and only that', async () => {
  const env = { navigator: { userAgent: 'Mozilla/5.0 (Macintosh)', gpu: { requestAdapter: async () => adapter(true) } } };
  const d = await probeDevice(plan, env);
  assert.equal(d.webgpu, true); assert.equal(d.f16, true); assert.equal(d.mobile, false);
  assert.equal(d.device_memory_gb, undefined); assert.equal(d.storage_free_bytes, undefined);
  assert.equal(d.bandwidth_Bps, undefined);  // no fetch in this environment
});

test('probeDevice finds a cached rung and measures the line', async () => {
  const last = plan.candidates[plan.candidates.length - 1];   // the smallest rung
  const store = new Set(last.files);
  let t = 0;
  const env = {
    navigator: { userAgent: 'x', gpu: { requestAdapter: async () => adapter(true) }, deviceMemory: 8,
                 storage: { estimate: async () => ({ quota: 5e10, usage: 1e9 }) } },
    caches: { open: async () => ({ match: async (u) => (store.has(u) ? {} : undefined) }) },
    performance: { now: () => (t += 500) },               // each call: +0.5 s
    fetch: async (url, o) => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(4_000_000) }),
  };
  const d = await probeDevice(plan, env);
  assert.deepEqual(d.cached, [`${last.model}|${last.dtype}`]);
  assert.equal(d.storage_free_bytes, 4.9e10);
  assert.equal(d.bandwidth_Bps, 16_000_000);             // two shards of 4 MB, together, in 0.5 s
  // 128 Mbit/s: no Gemma downloads within 180 s, so the cached rung wins.
  const r = chooseRung(plan, d);
  assert.equal(r.reason, 'cached');
  assert.equal(`${r.candidate.model}|${r.candidate.dtype}`, `${last.model}|${last.dtype}`);
});

test('a bandwidth probe too small or failed says nothing', async () => {
  const tiny = { performance: { now: (() => { let t = 0; return () => (t += 10); })() },
                 fetch: async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(1000) }) };
  assert.equal(await measureBandwidth('u', 4e6, tiny), undefined);
  assert.equal(await measureBandwidth('u', 4e6, { fetch: async () => { throw new Error('x'); } }), undefined);
});

test('the probe times from the first byte', async () => {
  // Each request: 1 s before its first byte (redirect, latency), then four
  // chunks of 1 MB, 0.25 s apart.
  let t = 0;
  const chunks = () => { let k = 0; return { read: async () => {
    if (k === 4) return { done: true };
    t += k++ === 0 ? 1000 : 250;
    return { done: false, value: new Uint8Array(1_000_000) }; } }; };
  const env = { performance: { now: () => t },
                fetch: async () => ({ ok: true, body: { getReader: chunks } }) };
  // First byte at 1 s, last at 1.75 s: 3 MB in 0.75 s, the 1 s before it
  // left out. Timed over the whole request, it would say 4 MB / 1.75 s.
  assert.equal(await measureBandwidth('a', 4e6, env), 4e6);
  assert.equal(await measureBandwidth([], 4e6, env), undefined);
});

const ex = [
  { text: "La parabole de l'éléphant raconte des aveugles qui touchent chacun une partie de l'animal." },
  { text: 'Un agent reçoit des permissions et exécute des actions.' },
];

test('a cited, supported answer is grounded', () => {
  const g = checkGrounding("Des aveugles touchent chacun une partie de l'éléphant [1]. Un agent exécute des actions [2].", ex);
  assert.deepEqual(g.cited, [1, 2]);
  assert.equal(g.grounded, true);
});

test('invented sentences, bad citations and uncited answers are not', () => {
  assert.equal(checkGrounding('La tarte tatin se cuit caramélisée au four [1].', ex).grounded, false);
  assert.equal(checkGrounding("Des aveugles touchent l'éléphant [7].", ex).grounded, false);
  assert.equal(checkGrounding("Des aveugles touchent chacun une partie de l'éléphant.", ex).grounded, false);
});

test('sentences split on strong punctuation', () => {
  assert.deepEqual(splitSentences('Une phrase. Une autre ! Et M. Dupont dit oui.'), ['Une phrase.', 'Une autre !', 'Et M. Dupont dit oui.']);
});
