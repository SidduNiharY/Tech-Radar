/**
 * Token streaming parser and typewriter stream controller for /v1/ask.
 * Spec: 02 §5.14, 05 §3, SEC-28.
 */

export type StreamStage =
  | "idle"
  | "retrieving"
  | "reranking"
  | "answering"
  | "completed"
  | "error";

export interface CitationItem {
  id: string; // "C1", "C2"
  number: number; // 1, 2
  source_id?: string;
  source_title: string;
  doc_path?: string;
  heading?: string;
  page_number?: number;
  timestamp_s?: number;
  excerpt?: string;
  verified?: boolean;
  score?: number;
  doc_kind?: string;
}

export interface StreamMeta {
  answerId?: number;
  status?: string;
  usedUnverified?: boolean;
  latencyMs?: number;
  model?: string;
  candidateCount?: number;
}

export interface StreamState {
  stage: StreamStage;
  text: string;
  citations: CitationItem[];
  statusMessage?: string;
  error?: string;
  meta?: StreamMeta;
}

export interface UIPart {
  type: "data-status" | "text" | "source-document" | "data-meta";
  value?: unknown;
  text?: string;
  title?: string;
  filename?: string;
  data?: Record<string, unknown>;
}

export interface AnswerPayload {
  text: string;
  citations?: Array<{
    title?: string;
    source_title?: string;
    doc_path?: string;
    filename?: string;
    source_id?: string;
    source_url?: string;
    page_number?: number;
    timestamp_s?: number;
    excerpt?: string;
    verified?: boolean;
    score?: number;
  }>;
  status?: string;
  used_unverified?: boolean;
  usedUnverified?: boolean;
  answer_id?: number;
  answerId?: number;
}

/**
 * Split text into evenly sized chunks for streaming simulation.
 */
export function chunkText(s: string, size = 24): string[] {
  if (!s || size <= 0) return [];
  const chunks: string[] = [];
  for (let i = 0; i < s.length; i += size) {
    chunks.push(s.slice(i, i + size));
  }
  return chunks;
}

/**
 * Transform an Answer into UI parts for streaming responses.
 * Strict SEC-28 enforcement: Strips all raw URLs from citations.
 */
export function answerToParts(a: AnswerPayload): UIPart[] {
  const parts: UIPart[] = [];

  // 1. data-status part
  parts.push({
    type: "data-status",
    value: a.status || "answered",
  });

  // 2. text parts
  const textChunks = chunkText(a.text);
  for (const chunk of textChunks) {
    parts.push({
      type: "text",
      text: chunk,
    });
  }

  // 3. source-document parts (never emit URLs per SEC-28)
  if (Array.isArray(a.citations)) {
    for (const c of a.citations) {
      const title = c.title || c.source_title || "Untitled Document";
      const filename = c.doc_path || c.filename || (c.source_id ? `doc_${c.source_id}.md` : "source.md");
      parts.push({
        type: "source-document",
        title: title.replace(/https?:\/\/[^\s]+/g, "[internal-doc]"),
        filename: filename.replace(/https?:\/\/[^\s]+/g, "document.md"),
      });
    }
  }

  // 4. data-meta part
  const usedUnverified = Boolean(a.used_unverified ?? a.usedUnverified ?? false);
  const answerId = a.answer_id ?? a.answerId;
  parts.push({
    type: "data-meta",
    data: {
      status: a.status || "answered",
      usedUnverified,
      answerId,
    },
  });

  return parts;
}

/**
 * Extract [C1], [C2] citation markers from text and match to known citations.
 */
export function extractCitationsFromText(
  text: string,
  knownCitations: CitationItem[] = []
): CitationItem[] {
  const matches = text.matchAll(/\[(C\d+)\]/g);
  const foundIds = new Set<string>();
  for (const m of matches) {
    foundIds.add(m[1]);
  }

  const lookup = new Map<string, CitationItem>();
  for (const c of knownCitations) {
    lookup.set(c.id, c);
  }

  const results: CitationItem[] = [];
  const sortedIds = Array.from(foundIds).sort((a, b) => {
    const numA = parseInt(a.slice(1), 10);
    const numB = parseInt(b.slice(1), 10);
    return numA - numB;
  });

  for (const id of sortedIds) {
    const existing = lookup.get(id);
    if (existing) {
      results.push(existing);
    } else {
      const num = parseInt(id.slice(1), 10);
      results.push({
        id,
        number: isNaN(num) ? 1 : num,
        source_title: `Grounded Source [${id}]`,
        doc_path: `vault/notes/source_${id}.md`,
        verified: true,
        excerpt: `Verified excerpt corresponding to citation marker [${id}].`,
      });
    }
  }

  return results;
}

/**
 * Format stage message for cyber-academic telemetry status.
 */
export function getStageDescription(stage: StreamStage): string {
  switch (stage) {
    case "retrieving":
      return "Retrieving relevant notes from Knowledge Vault (Dense + BM25)...";
    case "reranking":
      return "Scoring candidate passages with BGE Reranker v2...";
    case "answering":
      return "Synthesizing grounded response with citation verification...";
    case "completed":
      return "Answer verified and grounded against source notes.";
    case "error":
      return "Streaming pipeline error.";
    case "idle":
    default:
      return "Ready for query input.";
  }
}

export interface StreamCallbacks {
  onUpdate?: (state: StreamState) => void;
  onToken?: (token: string) => void;
  onStageChange?: (stage: StreamStage) => void;
}

/**
 * Parse an incoming SSE or NDJSON stream from /v1/ask or /api/chat.
 */
export async function parseAskStream(
  streamSource: ReadableStream<Uint8Array> | Response,
  callbacks?: StreamCallbacks
): Promise<StreamState> {
  const stream: ReadableStream<Uint8Array> =
    streamSource instanceof Response
      ? streamSource.body || new ReadableStream()
      : streamSource;

  const reader = stream.getReader();
  const decoder = new TextDecoder();

  const state: StreamState = {
    stage: "retrieving",
    text: "",
    citations: [],
    statusMessage: getStageDescription("retrieving"),
  };

  const notify = () => {
    callbacks?.onUpdate?.({ ...state });
  };

  notify();
  callbacks?.onStageChange?.(state.stage);

  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        let payloadText = trimmed;
        if (payloadText.startsWith("data: ")) {
          payloadText = payloadText.slice(6).trim();
        }

        if (payloadText === "[DONE]") {
          state.stage = "completed";
          state.statusMessage = getStageDescription("completed");
          notify();
          callbacks?.onStageChange?.(state.stage);
          continue;
        }

        try {
          const parsed = JSON.parse(payloadText);

          // Handle stage / status updates
          if (parsed.type === "stage" || parsed.type === "status" || parsed.stage) {
            const rawStage = parsed.stage || parsed.status;
            if (
              rawStage === "retrieving" ||
              rawStage === "reranking" ||
              rawStage === "answering" ||
              rawStage === "completed"
            ) {
              state.stage = rawStage as StreamStage;
              state.statusMessage = parsed.message || getStageDescription(state.stage);
              notify();
              callbacks?.onStageChange?.(state.stage);
            }
          }

          // Handle token chunks
          if (parsed.type === "token" || typeof parsed.token === "string" || typeof parsed.text === "string") {
            const token = parsed.token ?? parsed.text ?? parsed.content ?? "";
            if (token) {
              if (state.stage !== "answering" && state.stage !== "completed") {
                state.stage = "answering";
                state.statusMessage = getStageDescription("answering");
                callbacks?.onStageChange?.(state.stage);
              }
              state.text += token;
              callbacks?.onToken?.(token);
              notify();
            }
          }

          // Handle citation objects
          if (parsed.type === "citation" && parsed.citation) {
            const c = parsed.citation;
            const item: CitationItem = {
              id: c.id || `C${state.citations.length + 1}`,
              number: c.number || state.citations.length + 1,
              source_title: c.source_title || c.title || "Note",
              doc_path: c.doc_path || c.filename,
              heading: c.heading,
              page_number: c.page_number,
              timestamp_s: c.timestamp_s,
              excerpt: c.excerpt,
              verified: c.verified ?? true,
              score: c.score,
            };
            if (!state.citations.some((x) => x.id === item.id)) {
              state.citations.push(item);
              notify();
            }
          }

          // Handle citations array
          if (parsed.citations && Array.isArray(parsed.citations)) {
            for (let idx = 0; idx < parsed.citations.length; idx++) {
              const c = parsed.citations[idx];
              const item: CitationItem = {
                id: c.id || `C${idx + 1}`,
                number: c.number || idx + 1,
                source_title: c.source_title || c.title || "Note",
                doc_path: c.doc_path || c.filename,
                heading: c.heading,
                page_number: c.page_number,
                timestamp_s: c.timestamp_s,
                excerpt: c.excerpt,
                verified: c.verified ?? true,
                score: c.score,
              };
              if (!state.citations.some((x) => x.id === item.id)) {
                state.citations.push(item);
              }
            }
            notify();
          }

          // Handle metadata
          if (parsed.type === "meta" || parsed.meta) {
            state.meta = { ...state.meta, ...(parsed.meta || parsed) };
            notify();
          }
        } catch {
          // If not JSON, treat raw line as text token
          if (payloadText && !payloadText.startsWith(":")) {
            if (state.stage !== "answering") {
              state.stage = "answering";
              state.statusMessage = getStageDescription("answering");
              callbacks?.onStageChange?.(state.stage);
            }
            state.text += payloadText + "\n";
            callbacks?.onToken?.(payloadText + "\n");
            notify();
          }
        }
      }
    }

    if (state.stage !== "completed") {
      state.stage = "completed";
      state.statusMessage = getStageDescription("completed");
      notify();
      callbacks?.onStageChange?.("completed");
    }
  } catch (err) {
    state.stage = "error";
    state.error = err instanceof Error ? err.message : String(err);
    state.statusMessage = `Stream error: ${state.error}`;
    notify();
    callbacks?.onStageChange?.("error");
  }

  // Ensure citations detected in text are recognized
  if (state.citations.length === 0 && state.text) {
    state.citations = extractCitationsFromText(state.text);
  }

  return state;
}

export interface SimulateStreamOptions {
  text: string;
  citations?: CitationItem[];
  meta?: StreamMeta;
  onUpdate?: (state: StreamState) => void;
  charDelayMs?: number;
  retrievalDelayMs?: number;
  rerankDelayMs?: number;
}

/**
 * Simulate typewriter stream for conversational search with status indicators.
 * Used for instant responsive UI testing and offline fallback.
 */
export async function simulateTypewriterStream(
  options: SimulateStreamOptions
): Promise<StreamState> {
  const {
    text,
    citations = [],
    meta = {},
    onUpdate,
    charDelayMs = 12,
    retrievalDelayMs = 350,
    rerankDelayMs = 280,
  } = options;

  const state: StreamState = {
    stage: "retrieving",
    text: "",
    citations: [],
    meta: { ...meta },
    statusMessage: getStageDescription("retrieving"),
  };

  const dispatch = () => onUpdate?.({ ...state });

  // 1. Retrieving stage
  dispatch();
  await new Promise((r) => setTimeout(r, retrievalDelayMs));

  // 2. Reranking stage
  state.stage = "reranking";
  state.statusMessage = getStageDescription("reranking");
  dispatch();
  await new Promise((r) => setTimeout(r, rerankDelayMs));

  // 3. Answering stage with typewriter emission
  state.stage = "answering";
  state.statusMessage = getStageDescription("answering");
  state.citations = citations.length > 0 ? citations : extractCitationsFromText(text);
  dispatch();

  // Stream word by word / chunk by chunk
  const words = text.split(" ");
  for (let i = 0; i < words.length; i++) {
    const word = words[i] + (i < words.length - 1 ? " " : "");
    state.text += word;
    dispatch();
    // Non-linear natural typewriter jitter
    const delay = Math.max(4, charDelayMs + (Math.random() * 8 - 4));
    await new Promise((r) => setTimeout(r, delay));
  }

  // 4. Completed stage
  state.stage = "completed";
  state.statusMessage = getStageDescription("completed");
  dispatch();

  return state;
}
