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

// --------------------------------------------------- minimal widget --

const UI = {
  fr: { searching: 'Recherche…', unknown: 'Je ne sais pas répondre.',
        unknownWhy: 'Le corpus ne traite pas cette question, ou de trop loin.',
        quota: 'Trop de questions en peu de temps. Réessayez plus tard.',
        offline: 'La recherche ne répond pas.', answer: 'Réponse', sources: 'D’après : ' },
  en: { searching: 'Searching…', unknown: 'I cannot answer that.',
        unknownWhy: 'The corpus does not take up this question, or only from too far off.',
        quota: 'Too many questions in a short time. Try again later.',
        offline: 'Search is not responding.', answer: 'Answer', sources: 'Drawn from: ' },
};

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Wire a <form> with an <input>: answers and excerpts go into `output`.
 * Enough for a demo or a simple site; build your own with WebSearch for more.
 */
export function mount(form, output, options) {
  const ws = new WebSearch(options);
  const t = UI[options.lang] || UI.en;
  const input = form.querySelector('input');
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
  };
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const q = input.value.trim();
    if (!q) return;
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
