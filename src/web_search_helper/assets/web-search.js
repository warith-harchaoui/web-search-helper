// web-search-helper — browser client. https://github.com/warith-harchaoui/web-search-helper
// BSD 3-Clause licence, Warith Harchaoui.
//
// Plain ES module, no build step. It does two things in the page:
//   1. embeds the question with transformers.js (the corpus never comes to
//      the browser; only the question's vector goes to the server);
//   2. asks search.php, and optionally composes an extractive answer from the
//      excerpts it returns — sentences of the corpus, verbatim, never a word
//      added.
//
//   import { WebSearch, composeAnswer } from './web-search.js';
//   const ws = new WebSearch({ endpoint: 'search.php', lang: 'fr',
//                              model: 'Xenova/paraphrase-multilingual-MiniLM-L12-v2' });
//   const r = await ws.ask('Quelle est la parabole de l’éléphant ?', {
//     onLexical: (first) => { /* quick answer from words alone, if sure */ } });
//   if (!r.sure) { /* "I cannot answer": the server returned nothing */ }
//   const answer = await composeAnswer(r, { lang: 'fr', embed: ws });

const TRANSFORMERS = 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';

export class SearchError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

export class WebSearch {
  /**
   * @param {object} o
   * @param {string} o.endpoint  URL of search.php
   * @param {string} o.lang      language of the index to query
   * @param {string} [o.model]   transformers.js model, twin of the index's model
   * @param {string} [o.transformersUrl]  where to import transformers.js from
   */
  constructor({ endpoint, lang, model = 'Xenova/paraphrase-multilingual-MiniLM-L12-v2',
                transformersUrl = TRANSFORMERS }) {
    this.endpoint = endpoint;
    this.lang = lang;
    this.model = model;
    this.transformersUrl = transformersUrl;
    this._pipe = null;
    this.qv = null;
  }

  /** Load the model once; later calls reuse it (and the browser caches it). */
  pipeline() {
    if (!this._pipe) {
      this._pipe = import(this.transformersUrl).then((mod) => {
        mod.env.allowLocalModels = false;
        return mod.pipeline('feature-extraction', this.model);
      });
      // A failed load must not stick: the next question retries.
      this._pipe.catch(() => { this._pipe = null; });
    }
    return this._pipe;
  }

  /** Normalised vectors, one Float32Array per text. */
  async embed(texts) {
    const pipe = await this.pipeline();
    const out = await pipe(texts, { pooling: 'mean', normalize: true });
    const dim = out.dims[out.dims.length - 1];
    return texts.map((_, k) => out.data.slice(k * dim, (k + 1) * dim));
  }

  async query(q, qv) {
    const body = { lang: this.lang, q };
    if (qv) body.v = Array.from(qv);
    let res;
    try {
      res = await fetch(this.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e) {
      throw new SearchError('network', String(e));
    }
    if (res.status === 429) throw new SearchError('quota', 'too many requests');
    if (!res.ok) throw new SearchError('server', 'HTTP ' + res.status);
    return res.json();
  }

  /**
   * Two calls: words first (fast, before the model has loaded), then words
   * and meaning. A lexical "sure" is final: the verdict is an OR, meaning can
   * only add to it. If the model cannot load, the lexical result stands.
   */
  async ask(q, { onLexical } = {}) {
    const first = await this.query(q, null);
    if (onLexical) onLexical(first);
    let qv;
    try {
      [qv] = await this.embed([q]);
    } catch (e) {
      this.qv = null;
      return { ...first, semantic: false };
    }
    this.qv = qv;
    const full = await this.query(q, qv);
    return { ...full, semantic: true, qv };
  }
}

// ------------------------------------------------- extractive answer --
// Sentences of the excerpts, scored by meaning and words, chosen by maximal
// marginal relevance, read in corpus order. Nothing is rewritten except
// what only makes sense inside the original paragraph (a leading "Thus",
// a "(see above)").

const RULES = {
  fr: {
    anaphora: /^(?:elle|elles|il|ils|celui|celle|ceux|celles|cela|ceci|ce|c'est|cette|ces|cet|leur|leurs|son|sa|ses|y|en|or|donc|ainsi|puis|ensuite|enfin|pourtant|cependant|néanmoins|d'où|aussi|mais|car)\b/i,
    meta: /^(?:ce (?:chapitre|livre|texte|point|passage)|cette (?:partie|section|sous-section)|la (?:partie|section) (?:précédente|suivante)|nous (?:verrons|reviendrons|allons|venons)|reprenons|rappelons|revenons|on l'a (?:vu|dit)|comme (?:on|nous) l'avons)\b/i,
    lead: /^(?:or|donc|ainsi|aussi|puis|ensuite|enfin|pourtant|cependant|néanmoins|toutefois|d'où|en effet|de fait|dès lors|c'est pourquoi|par ailleurs|en revanche|au contraire)\b[\s,]*/i,
    xref: /\s*\((?:voir|cf\.?)\b[^)]*\)|\s*\(§[^)]*\)/gi,
  },
  en: {
    anaphora: /^(?:it|they|this|that|these|those|its|their|thus|hence|so|yet|but|however|therefore|then)\b/i,
    meta: /^(?:this (?:chapter|book|part|section)|the (?:previous|next) (?:part|section)|we (?:shall|will) (?:see|return)|let us (?:return|recall)|as we (?:saw|have seen))\b/i,
    lead: /^(?:thus|hence|so|yet|however|therefore|moreover|besides|indeed|in fact|that said|still)\b[\s,]*/i,
    xref: /\s*\((?:see|cf\.?)\b[^)]*\)|\s*\(§[^)]*\)/gi,
  },
};

const ABBREV = /(?:\b(?:M|MM|Mme|Dr|Pr|cf|etc|vs|v|art|chap|éd|no|St|p)\.|\b[A-ZÀ-Ż]\.)$/;

export function splitSentences(text) {
  const parts = text.split(/(?<=[.!?…])\s+(?=[«"“(]?[\p{Lu}0-9])/u);
  const out = [];
  for (const s of parts) {
    if (out.length && ABBREV.test(out[out.length - 1].trim())) out[out.length - 1] += ' ' + s;
    else out.push(s);
  }
  return out.map((s) => s.trim()).filter(Boolean);
}

function fold(s) { return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
function words(s) { return fold(s).split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 2); }

function isProse(s, rules) {
  const letters = (s.match(/\p{L}/gu) || []).length;
  const digits = (s.match(/[0-9]/g) || []).length;
  const t = s.trim();
  return letters >= 25 && digits <= letters / 4 && !/^[0-9]/.test(t)
    && /[.!?…]$/.test(t) && !(rules && rules.meta.test(t));
}

function tidy(s, rules) {
  if (!rules) return s.trim();
  let x = s.replace(rules.xref, '');
  const cut = x.replace(rules.lead, '');
  if (cut.length > 25) x = cut.charAt(0).toUpperCase() + cut.slice(1);
  return x.replace(/\s{2,}/g, ' ').replace(/\s+([,;:.!?…])/g, '$1').trim();
}

/**
 * Compose an answer from a `sure` result.
 * @param {object} result   what WebSearch.ask returned
 * @param {object} [o]
 * @param {string} [o.lang]     'fr' or 'en' enable the tidying rules
 * @param {WebSearch} [o.embed] re-score the best sentences one by one
 * @param {number} [o.maxWords=130]
 * @param {number} [o.maxSentences=5]
 * @returns {Promise<{text: string, sources: object[]}|null>}
 */
export async function composeAnswer(result, { lang, embed, maxWords = 130, maxSentences = 5 } = {}) {
  if (!result || !result.sure || !result.hits || !result.hits.length) return null;
  const rules = RULES[lang];
  const terms = new Set(result.terms || []);
  const nTerms = terms.size;
  const cands = [];
  result.hits.forEach((h, rank) => {
    const sentences = splitSentences(h.text);
    let cursor = 0;
    sentences.forEach((s, pos) => {
      let at = h.text.indexOf(s, cursor);
      if (at < 0) at = cursor;
      cursor = at + s.length;
      let f = 0;
      while (f < h.o.length - 1 && h.o[f] <= at) f++;
      const toks = words(s);
      if (!toks.length || !isProse(s, rules)) return;
      const uniq = new Set(toks);
      let matched = 0;
      terms.forEach((w) => { if (uniq.has(w)) matched++; });
      const cov = nTerms ? matched / nTerms : 0;
      const occ = toks.filter((w) => terms.has(w)).length;
      const cosW = h.cos[f] || 0;
      cands.push({ s, toks: uniq, words: s.split(/\s+/).length, rank, pos,
                   prev: pos > 0 ? sentences[pos - 1] : null, hit: h, cosW,
                   score: cosW + 0.6 * cov * cov + 0.02 * occ + 0.15 / (rank + 1) });
    });
  });
  if (!cands.length) return null;

  // Second pass: the best sentences scored one by one by the model.
  if (embed && result.qv) {
    const top = cands.slice().sort((a, b) => b.score - a.score).slice(0, 40);
    try {
      const vs = await embed.embed(top.map((c) => c.s));
      top.forEach((c, k) => {
        let dot = 0;
        for (let d = 0; d < result.qv.length; d++) dot += result.qv[d] * vs[k][d];
        c.score += dot - c.cosW + 0.10 * Math.min(1, c.toks.size / 18);
      });
    } catch (e) { /* window scores stand */ }
  }

  cands.sort((a, b) => b.score - a.score);
  const picked = [];
  let rest = cands.slice(0, 60);
  let total = 0;
  while (picked.length < maxSentences && rest.length) {
    let best = -1, bestNote = -Infinity;
    rest.forEach((c, i) => {
      if (total + c.words > maxWords) return;
      let redund = 0;
      picked.forEach((p) => {
        let common = 0;
        c.toks.forEach((w) => { if (p.toks.has(w)) common++; });
        redund = Math.max(redund, c.toks.size ? common / c.toks.size : 0);
      });
      if (redund > 0.6) return;
      const note = 0.7 * c.score - 0.3 * redund;
      if (note > bestNote) { bestNote = note; best = i; }
    });
    if (best < 0) break;
    const c = rest.splice(best, 1)[0];
    picked.push(c);
    total += c.words;
  }
  if (!picked.length) return null;

  const ordered = [picked[0]].concat(picked.slice(1).sort((a, b) => a.rank - b.rank || a.pos - b.pos));
  const said = new Set();
  const pieces = [];
  const kept = [];
  for (const c of ordered) {
    const key = c.s.trim();
    if (said.has(key)) continue;
    const prev = (c.prev || '').trim();
    if (rules && prev && !said.has(prev) && rules.anaphora.test(c.s)
        && total + prev.split(/\s+/).length <= maxWords + 25) {
      total += prev.split(/\s+/).length;
      said.add(prev);
      pieces.push(tidy(prev, rules) + ' ' + c.s);
    } else {
      pieces.push(tidy(c.s, rules));
    }
    said.add(key);
    kept.push(c);
  }
  const seen = new Set();
  const sources = [];
  for (const c of kept) {
    const key = c.hit.doc + '\u0000' + c.hit.section;
    if (!seen.has(key)) {
      seen.add(key);
      sources.push({ doc: c.hit.doc, section: c.hit.section, url: c.hit.url, meta: c.hit.meta });
    }
  }
  return { text: pieces.join(' '), sources };
}

// --------------------------------------------- written answer (LLM) --
// Optional. A small language model runs in the visitor's browser (WebGPU,
// through transformers.js 4) and rewrites the excerpts into an answer that
// cites them as [1], [2]… Nothing leaves the browser; the server is unchanged.
//
// WHICH model is not decided here. best-engine-ai-helper plans, in advance, an
// ordered ladder of candidates for the `rag-answer` usage (writer-plan.json:
// Gemma 4 E4B then E2B, each in q4f16 and q4, ranked by scores measured on
// the task, with exact files and sizes). The page walks the ladder down with what it measures:
// WebGPU and shader-f16, deviceMemory, storage, mobile and data saver, the
// cache, and the bandwidth OBSERVED on the model's own files. `chooseRung`
// is the twin of best_engine_ai_helper.browser.choose, and is tested against
// it.
//
// Three rules keep the answer honest:
//   - it only ever sees a `sure` result: the "I cannot answer" verdict is
//     taken before any model writes;
//   - it is told to use the excerpts only, and to say so when they fall short;
//   - every sentence it writes is checked against the excerpts it was given
//     (`grounded`); the page falls back to composeAnswer otherwise.

const TRANSFORMERS_V4 = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.2';
//: transformers.js keeps downloaded model files in this Cache Storage bucket.
const TJS_CACHE = 'transformers-cache';

/**
 * Walk the ladder for one device: the twin of best-engine's `browser.choose`.
 * `device` keys, all optional: webgpu, f16, mobile, save_data, effective_type,
 * device_memory_gb, storage_free_bytes, bandwidth_Bps, cached ("model|dtype").
 * @returns {{candidate: object|null, reason: string, seconds: number|null}}
 */
export function chooseRung(plan, device) {
  const pol = plan.policy;
  if (!device.webgpu) return { candidate: null, reason: 'webgpu', seconds: null };
  if (device.mobile) return { candidate: null, reason: 'mobile', seconds: null };
  if (device.save_data || pol.slow_networks.includes(device.effective_type)) {
    return { candidate: null, reason: 'network', seconds: null };
  }
  const cached = new Set(device.cached || []);
  const bandwidth = device.bandwidth_Bps || pol.unknown_bandwidth_Bps;
  let fitsDevice = false;
  for (const c of plan.candidates) {
    if (c.needs_f16 && !device.f16) continue;
    const mem = device.device_memory_gb;
    if (mem != null && c.min_device_memory_gb && mem < c.min_device_memory_gb) continue;
    if (cached.has(`${c.model}|${c.dtype}`)) return { candidate: c, reason: 'cached', seconds: 0 };
    const free = device.storage_free_bytes;
    if (free != null && free < c.bytes * pol.storage_margin) continue;
    fitsDevice = true;
    const seconds = c.bytes / bandwidth;
    if (seconds <= pol.max_download_s) {
      return { candidate: c, reason: 'ok', seconds: Math.round(seconds * 10) / 10 };
    }
  }
  return { candidate: null, reason: fitsDevice ? 'download' : 'device', seconds: null };
}

/**
 * What the page can learn about this machine and line, without downloading a
 * model. The bandwidth is measured on the model's own host, with a Range
 * request on the first file of `probeUrl`'s rung; the cache is read in the
 * bucket transformers.js writes. A signal the browser does not expose stays
 * undefined, and chooseRung does not hold it against the machine.
 * @param {object} plan
 * @param {object} [env]  the global object; injectable for tests
 */
export async function probeDevice(plan, env = globalThis) {
  const nav = env.navigator || {};
  const device = {};
  if (nav.gpu) {
    try {
      const adapter = await nav.gpu.requestAdapter();
      device.webgpu = !!adapter;
      device.f16 = !!(adapter && adapter.features && adapter.features.has('shader-f16'));
    } catch (e) { device.webgpu = false; }
  }
  device.mobile = nav.userAgentData ? !!nav.userAgentData.mobile
    : /Mobi|Android|iPhone|iPad/i.test(nav.userAgent || '');
  if (nav.connection) {
    device.save_data = !!nav.connection.saveData;
    device.effective_type = nav.connection.effectiveType;
  }
  if (typeof nav.deviceMemory === 'number') device.device_memory_gb = nav.deviceMemory;
  if (nav.storage && nav.storage.estimate) {
    try {
      const { quota, usage = 0 } = await nav.storage.estimate();
      if (quota) device.storage_free_bytes = quota - usage;
    } catch (e) { /* unknown */ }
  }
  device.cached = [];
  if (env.caches) {
    try {
      const cache = await env.caches.open(TJS_CACHE);
      for (const c of plan.candidates) {
        const hits = await Promise.all(c.files.map((u) => cache.match(u)));
        if (hits.every(Boolean)) device.cached.push(`${c.model}|${c.dtype}`);
      }
    } catch (e) { /* no cache access */ }
  }
  if (device.webgpu && !device.mobile && !device.save_data && plan.candidates.length) {
    device.bandwidth_Bps = await measureBandwidth(
      // A weight shard, not the small graph file: under a megabyte, latency
      // would dominate the measure.
      plan.candidates[plan.candidates.length - 1].files.find((u) => u.includes('.onnx_data'))
        || plan.candidates[plan.candidates.length - 1].files[0],
      plan.policy.probe_bytes, env);
  }
  return device;
}

/** Bytes per second over a Range request of `bytes` on `url`; undefined on failure. */
export async function measureBandwidth(url, bytes, env = globalThis) {
  if (!url || !env.fetch) return undefined;
  const now = () => (env.performance ? env.performance.now() : Date.now());
  try {
    const t0 = now();
    const res = await env.fetch(url, { headers: { Range: `bytes=0-${bytes - 1}` }, cache: 'no-store' });
    if (!res.ok) return undefined;
    const got = (await res.arrayBuffer()).byteLength;
    const seconds = (now() - t0) / 1000;
    // Under ~1 MB or ~50 ms, latency dominates and the figure means nothing.
    return got >= 1e6 && seconds > 0.05 ? got / seconds : undefined;
  } catch (e) {
    return undefined;
  }
}

const WRITER_PROMPTS = {
  fr: {
    system: 'Tu réponds à une question en t’appuyant UNIQUEMENT sur les extraits numérotés fournis. '
      + 'Cite chaque affirmation par le numéro de l’extrait entre crochets, par exemple [2]. '
      + 'N’ajoute aucune connaissance extérieure. Si les extraits ne suffisent pas, dis-le en une phrase. '
      + 'Réponds en français, en 120 mots au plus, sans titre ni liste.',
    excerpts: 'Extraits',
    question: 'Question',
  },
  en: {
    system: 'You answer a question using ONLY the numbered excerpts provided. '
      + 'Cite every claim with the excerpt number in square brackets, for example [2]. '
      + 'Add no outside knowledge. If the excerpts are not enough, say so in one sentence. '
      + 'Answer in English, in 120 words at most, with no heading or list.',
    excerpts: 'Excerpts',
    question: 'Question',
  },
};

export class Writer {
  /**
   * One rung of the plan, ready to load. Prefer `Writer.create(plan)`.
   * @param {object} rung   a plan candidate (model, dtype, loader, chat_kwargs, bytes)
   * @param {object} [o]
   * @param {string} [o.transformersUrl]
   * @param {(p: object) => void} [o.onProgress]  transformers.js download progress events
   */
  constructor(rung, { transformersUrl = TRANSFORMERS_V4, onProgress } = {}) {
    this.rung = rung;
    this.model = rung.model;
    this.dtype = rung.dtype;
    this.bytes = rung.bytes;
    this.transformersUrl = transformersUrl;
    this.onProgress = onProgress;
    this._ready = null;
  }

  /**
   * The Writer this machine and line can bear, or none.
   * @param {object|string} plan  the plan, or the URL of writer-plan.json
   * @returns {Promise<{writer: Writer|null, reason: string, seconds: number|null, device: object}>}
   */
  static async create(plan, options = {}) {
    if (typeof plan === 'string') plan = await (await fetch(plan)).json();
    const device = await probeDevice(plan);
    const r = chooseRung(plan, device);
    return { writer: r.candidate ? new Writer(r.candidate, options) : null,
             reason: r.reason, seconds: r.seconds, device };
  }

  load() {
    if (!this._ready) {
      this._ready = (async () => {
        const tf = await import(this.transformersUrl);
        const opts = { progress_callback: (p) => this.onProgress && this.onProgress(p) };
        // Gemma 4 keeps its chat template in the processor; text-only models
        // in the tokenizer. AutoModelForCausalLM loads Gemma 4 text-only.
        const chat = this.rung.loader === 'processor'
          ? await tf.AutoProcessor.from_pretrained(this.model, opts)
          : await tf.AutoTokenizer.from_pretrained(this.model, opts);
        const tokenizer = this.rung.loader === 'processor' ? chat.tokenizer : chat;
        const model = await tf.AutoModelForCausalLM.from_pretrained(this.model, {
          ...opts, device: 'webgpu', dtype: this.dtype,
        });
        return { tf, chat, tokenizer, model };
      })();
      this._ready.catch(() => { this._ready = null; });
    }
    return this._ready;
  }

  /**
   * Write an answer from a `sure` search result.
   * @param {object} result   what WebSearch.ask returned
   * @param {object} o
   * @param {string} o.question
   * @param {string} o.lang     'fr' or 'en' (other languages use the English prompt)
   * @param {number} [o.maxExcerpts=6]
   * @param {number} [o.maxNewTokens=320]
   * @param {(text: string) => void} [o.onText]  streamed text so far
   * @returns {Promise<{text: string, cited: number[], grounded: boolean, unsupported: string[], excerpts: object[]}|null>}
   */
  async write(result, { question, lang, maxExcerpts = 6, maxNewTokens = 320, onText } = {}) {
    if (!result || !result.sure || !result.hits || !result.hits.length) return null;
    const P = WRITER_PROMPTS[lang] || WRITER_PROMPTS.en;
    const excerpts = result.hits.slice(0, maxExcerpts);
    const block = excerpts.map((h, k) =>
      `[${k + 1}] (${h.section || h.doc}) ${h.before ? '… ' : ''}${h.text}${h.after ? ' …' : ''}`).join('\n\n');
    const messages = [
      { role: 'system', content: P.system },
      { role: 'user', content: `${P.excerpts}:\n\n${block}\n\n${P.question}: ${question}` },
    ];
    const { tf, chat, tokenizer, model } = await this.load();
    const prompt = chat.apply_chat_template(messages, {
      ...(this.rung.chat_kwargs || {}), add_generation_prompt: true, tokenize: false,
    });
    const inputs = tokenizer(prompt, { add_special_tokens: false });
    let streamed = '';
    const streamer = new tf.TextStreamer(tokenizer, {
      skip_prompt: true,
      skip_special_tokens: true,
      callback_function: (t) => { streamed += t; if (onText) onText(streamed); },
    });
    const out = await model.generate({ ...inputs, max_new_tokens: maxNewTokens, do_sample: false, streamer });
    const text = tokenizer.batch_decode(out.slice(null, [inputs.input_ids.dims.at(-1), null]),
      { skip_special_tokens: true })[0].trim();
    return { text, excerpts, ...checkGrounding(text, excerpts) };
  }
}

/**
 * Which sentences of a written answer the excerpts support.
 * A sentence is supported when at least half of its content words (folded,
 * more than three letters) appear in the excerpts it cites, or in all the
 * excerpts when it cites none. Citations to excerpts that do not exist count
 * against it.
 */
export function checkGrounding(text, excerpts) {
  const vocab = excerpts.map((h) => new Set(words(h.text)));
  const all = new Set(vocab.flatMap((s) => [...s]));
  const cited = new Set();
  const unsupported = [];
  for (const s of splitSentences(text.replace(/\n+/g, ' '))) {
    const refs = [...s.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
    refs.forEach((n) => cited.add(n));
    if (refs.some((n) => n < 1 || n > excerpts.length)) { unsupported.push(s); continue; }
    const pool = refs.length ? new Set(refs.flatMap((n) => [...vocab[n - 1]])) : all;
    const content = words(s.replace(/\[\d+\]/g, '')).filter((w) => w.length > 3);
    if (!content.length) continue;
    const hit = content.filter((w) => pool.has(w)).length;
    if (hit / content.length < 0.5) unsupported.push(s);
  }
  return { cited: [...cited].sort((a, b) => a - b), grounded: unsupported.length === 0 && cited.size > 0, unsupported };
}

// --------------------------------------------------- minimal widget --

const UI = {
  fr: { searching: 'Recherche…', unknown: 'Je ne sais pas répondre.',
        unknownWhy: 'Le corpus ne traite pas cette question, ou de trop loin.',
        quota: 'Trop de questions en peu de temps. Réessayez plus tard.',
        offline: 'La recherche ne répond pas.', answer: 'Réponse', sources: 'D’après : ',
        write: (m, gb, cached) => `Rédiger une réponse avec ${m} (dans votre navigateur ; `
          + (cached ? 'modèle déjà téléchargé)' : `${gb.toFixed(1).replace('.', ',')} Go à télécharger la première fois)`),
        loading: 'Chargement du modèle…', writing: 'Rédaction…',
        written: 'Réponse rédigée par un modèle de langue dans votre navigateur, à partir des extraits numérotés ci-dessous.',
        rejected: 'La réponse rédigée a été écartée : certaines phrases ne s’appuient pas sur les extraits.',
        failed: 'Le modèle n’a pas pu se charger dans ce navigateur.' },
  en: { searching: 'Searching…', unknown: 'I cannot answer that.',
        unknownWhy: 'The corpus does not take up this question, or only from too far off.',
        quota: 'Too many questions in a short time. Try again later.',
        offline: 'Search is not responding.', answer: 'Answer', sources: 'Drawn from: ',
        write: (m, gb, cached) => `Write an answer with ${m} (in your browser; `
          + (cached ? 'model already downloaded)' : `${gb.toFixed(1)} GB to download the first time)`),
        loading: 'Loading the model…', writing: 'Writing…',
        written: 'Answer written by a language model in your browser, from the numbered excerpts below.',
        rejected: 'The written answer was set aside: some sentences are not supported by the excerpts.',
        failed: 'The model could not load in this browser.' },
};

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Wire a <form> with an <input>: answers and excerpts go into `output`.
 * Enough for a demo or a simple site; build your own with WebSearch for more.
 * `options.writer: true` adds a button that writes an answer with the model
 * the plan picks for this machine (`writer-plan.json` next to this file, or
 * `options.writerPlan`), shown only when one fits and the result is `sure`.
 */
export function mount(form, output, options) {
  const ws = new WebSearch(options);
  const t = UI[options.lang] || UI.en;
  const input = form.querySelector('input');
  // The plan sits next to this file unless the page says otherwise.
  const planUrl = options.writerPlan || new URL('writer-plan.json', import.meta.url).href;
  const writerReady = options.writer
    ? Writer.create(planUrl).then((x) => { if (x.writer) x.writer.cached = x.reason === 'cached'; return x.writer; })
      .catch(() => null)
    : Promise.resolve(null);
  let question = '';
  const offerWriter = async (r) => {
    if (!r.sure || r.semantic === undefined) return;  // final result only
    const writer = await writerReady;
    if (!writer) return;
    const box = document.createElement('section');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = t.write(writer.model.split('/').pop().replace(/-ONNX$/, ''), writer.bytes / 1e9, writer.cached);
    box.appendChild(btn);
    output.prepend(box);
    btn.addEventListener('click', async () => {
      const note = document.createElement('p');
      const body = document.createElement('p');
      box.replaceChildren(note, body);
      note.innerHTML = `<small>${esc(t.loading)}</small>`;
      // Per-file events, summed against the rung's whole download: a model
      // comes in several files, and one file's percentage misleads.
      const loaded = {};
      writer.onProgress = (p) => {
        if (p.status === 'progress' && p.file) {
          loaded[p.file] = p.loaded || 0;
          const sum = Object.values(loaded).reduce((a, b) => a + b, 0);
          note.innerHTML = `<small>${esc(t.loading)} ${Math.min(100, Math.round((100 * sum) / writer.bytes))} %</small>`;
        }
      };
      try {
        await writer.load();
        note.innerHTML = `<small>${esc(t.writing)}</small>`;
        const w = await writer.write(r, { question, lang: options.lang,
          onText: (txt) => { body.textContent = txt; } });
        if (w && w.grounded) {
          body.textContent = w.text;
          note.innerHTML = `<small>${esc(t.written)}</small>`;
        } else {
          body.textContent = '';
          note.innerHTML = `<small>${esc(t.rejected)}</small>`;
        }
      } catch (e) {
        note.innerHTML = `<small>${esc(t.failed)}</small>`;
      }
    });
  };
  const paint = async (r) => {
    if (!r.sure) {
      output.innerHTML = `<p><strong>${esc(t.unknown)}</strong></p><p>${esc(t.unknownWhy)}</p>`;
      return;
    }
    const a = await composeAnswer(r, { lang: options.lang, embed: r.semantic ? ws : null });
    const hits = r.hits.slice(0, 6).map((h) =>
      `<li><p><small>${h.url ? `<a href="${esc(h.url)}">` : ''}${esc(h.doc)}${h.section && h.section !== h.doc ? ' · ' + esc(h.section) : ''}${h.url ? '</a>' : ''}</small></p>`
      + `<p>${h.before ? '… ' : ''}${esc(h.text)}${h.after ? ' …' : ''}</p></li>`).join('');
    output.innerHTML = (a ? `<section><h3>${esc(t.answer)}</h3><p>${esc(a.text)}</p>`
      + `<p><small>${esc(t.sources)}${a.sources.map((s) => esc(s.section || s.doc)).join(' ; ')}</small></p></section>` : '')
      + `<ol>${hits}</ol>`;
    offerWriter(r);
  };
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    question = q;
    output.textContent = t.searching;
    try {
      const r = await ws.ask(q, { onLexical: (first) => { if (first.sure) paint(first); } });
      await paint(r);
    } catch (e) {
      output.textContent = e.code === 'quota' ? t.quota : t.offline;
    }
  });
  return ws;
}
