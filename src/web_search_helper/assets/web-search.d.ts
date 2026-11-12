// Types for web-search.js. BSD 3-Clause licence, Warith Harchaoui.

export interface Hit {
  doc: string;
  section: string;
  url: string;
  meta: Record<string, unknown>;
  /** An excerpt, never the whole passage. */
  text: string;
  /** End offsets of the windows inside `text`. */
  o: number[];
  /** Cosine of each window with the question (0 when no vector was sent). */
  cos: number[];
  /** True when the excerpt starts after, or ends before, the passage does. */
  before: boolean;
  after: boolean;
}

export interface SearchResult {
  /** False: the corpus does not treat the question, and nothing is returned. */
  sure: boolean;
  /** The words actually searched (typos replaced by their neighbours). */
  terms: string[];
  hits?: Hit[];
  /** Whether the meaning route took part (the model loaded). */
  semantic?: boolean;
  qv?: Float32Array;
}

export interface Answer {
  text: string;
  sources: { doc: string; section: string; url: string; meta: Record<string, unknown> }[];
}

export class SearchError extends Error {
  code: 'network' | 'quota' | 'server';
}

export interface WebSearchOptions {
  endpoint: string;
  lang: string;
  model?: string;
  transformersUrl?: string;
}

export class WebSearch {
  constructor(options: WebSearchOptions);
  qv: Float32Array | null;
  embed(texts: string[]): Promise<Float32Array[]>;
  query(q: string, qv?: Float32Array | null): Promise<SearchResult>;
  ask(q: string, o?: { onLexical?: (first: SearchResult) => void }): Promise<SearchResult>;
}

export function composeAnswer(
  result: SearchResult,
  o?: { lang?: string; embed?: WebSearch | null; maxWords?: number; maxSentences?: number },
): Promise<Answer | null>;

export function splitSentences(text: string): string[];

export function mount(form: HTMLFormElement, output: HTMLElement, options: WebSearchOptions): WebSearch;
