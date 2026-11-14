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

/** One rung of best-engine-ai-helper's ladder (writer-plan.json). */
export interface Rung {
  model: string;
  family: string;
  dtype: 'q4f16' | 'q4' | string;
  bytes: number;
  needs_f16: boolean;
  min_device_memory_gb: number | null;
  files: string[];
  loader: 'processor' | 'tokenizer';
  chat_kwargs: Record<string, unknown>;
  params_b: number;
  license: string;
  measured: number | null;
}

export interface WriterPlan {
  usage: string;
  runtime: 'transformers.js';
  transformers: string;
  languages: string[];
  policy: { max_download_s: number; unknown_bandwidth_Bps: number; probe_bytes: number;
            storage_margin: number; slow_networks: string[] };
  min_score: number;
  candidates: Rung[];
  /** Models left out of the ladder, and why (languages, or measured below min_score). */
  excluded: { model: string; reason: string }[];
}

/** What the page measured; every key optional, an absent signal is never held against the machine. */
export interface Device {
  webgpu?: boolean; f16?: boolean; mobile?: boolean; save_data?: boolean; effective_type?: string;
  device_memory_gb?: number; storage_free_bytes?: number; bandwidth_Bps?: number; cached?: string[];
}

export type Reason = 'ok' | 'cached' | 'webgpu' | 'mobile' | 'network' | 'device' | 'download';

/** The twin of best_engine_ai_helper.browser.choose. */
export function chooseRung(plan: WriterPlan, device: Device): { candidate: Rung | null; reason: Reason; seconds: number | null };
export function probeDevice(plan: WriterPlan, env?: typeof globalThis): Promise<Device>;
export function measureBandwidth(urls: string | string[], bytes: number, env?: typeof globalThis): Promise<number | undefined>;

export interface WrittenAnswer {
  text: string;
  cited: number[];
  /** Every sentence is supported by the excerpts it cites, and at least one is cited. */
  grounded: boolean;
  unsupported: string[];
  excerpts: Hit[];
}

export class Writer {
  constructor(rung: Rung, o?: { transformersUrl?: string; onProgress?: (p: unknown) => void });
  rung: Rung; model: string; dtype: string; bytes: number;
  onProgress?: (p: unknown) => void;
  static create(plan: WriterPlan | string, o?: { transformersUrl?: string; onProgress?: (p: unknown) => void }):
    Promise<{ writer: Writer | null; reason: Reason; seconds: number | null; device: Device }>;
  load(): Promise<unknown>;
  write(result: SearchResult, o: { question: string; lang: string; maxExcerpts?: number; maxNewTokens?: number;
                                   onText?: (text: string) => void }): Promise<WrittenAnswer | null>;
}

export function checkGrounding(text: string, excerpts: Hit[]): { cited: number[]; grounded: boolean; unsupported: string[] };

export function mount(form: HTMLFormElement, output: HTMLElement,
  options: WebSearchOptions & { writer?: boolean; writerPlan?: string }): WebSearch;
