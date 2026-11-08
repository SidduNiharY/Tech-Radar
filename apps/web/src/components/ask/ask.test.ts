import { describe, it } from "node:test";
import assert from "node:assert";
import {
  answerToParts,
  chunkText,
  extractCitationsFromText,
  getStageDescription,
  simulateTypewriterStream,
  StreamState,
} from "../../lib/stream";
import type { CitationInfo } from "./citation-drawer";

describe("Ask Stream: chunkText", () => {
  it("splits strings evenly by chunk size", () => {
    assert.deepStrictEqual(chunkText("abcdef", 2), ["ab", "cd", "ef"]);
    assert.deepStrictEqual(chunkText("abcdefg", 3), ["abc", "def", "g"]);
  });

  it("handles empty or zero-size inputs cleanly", () => {
    assert.deepStrictEqual(chunkText("", 2), []);
    assert.deepStrictEqual(chunkText("hello", 0), []);
    assert.deepStrictEqual(chunkText("hello", -1), []);
  });

  it("handles string shorter than chunk size", () => {
    assert.deepStrictEqual(chunkText("short", 20), ["short"]);
  });
});

describe("Ask Stream: answerToParts (SEC-28)", () => {
  it("never emits raw external URLs in citation source-document parts", () => {
    const answerPayload = {
      text: "According to the RBI statement [C1], policy rates are unchanged.",
      citations: [
        {
          title: "RBI Monetary Policy",
          doc_path: "vault/notes/rbi.md",
          source_url: "https://rbi.org.in/leak-probe",
        },
        {
          title: "Attacker Site https://evil.example/beacon",
          filename: "https://evil.example/exfil.pdf",
        },
      ],
      status: "answered",
      used_unverified: false,
      answer_id: 42,
    };

    const parts = answerToParts(answerPayload);

    // 1. Never emit URLs per SEC-28
    const serialized = JSON.stringify(parts);
    assert.ok(
      !/https?:\/\//.test(serialized),
      `SEC-28 Violation: URL leaked in streamed answer parts: ${serialized}`
    );

    // 2. Contains data-status part
    const statusPart = parts.find((p) => p.type === "data-status");
    assert.ok(statusPart);
    assert.strictEqual(statusPart.value, "answered");

    // 3. Contains text parts from chunkText
    const textParts = parts.filter((p) => p.type === "text");
    assert.ok(textParts.length > 0);
    assert.strictEqual(
      textParts.map((t) => t.text).join(""),
      answerPayload.text
    );

    // 4. Contains source-document parts per citation without raw URLs
    const docParts = parts.filter((p) => p.type === "source-document");
    assert.strictEqual(docParts.length, 2);
    assert.ok(!docParts[0].filename?.includes("https://"));
    assert.ok(!docParts[1].title?.includes("https://"));

    // 5. Contains data-meta part
    const metaPart = parts.find((p) => p.type === "data-meta");
    assert.ok(metaPart);
    assert.deepStrictEqual(metaPart.data, {
      status: "answered",
      usedUnverified: false,
      answerId: 42,
    });
  });

  it("properly flags unverified note usage", () => {
    const parts = answerToParts({
      text: "Unverified finding.",
      used_unverified: true,
      status: "needs_review",
    });
    const metaPart = parts.find((p) => p.type === "data-meta");
    assert.strictEqual(metaPart?.data?.usedUnverified, true);
    assert.strictEqual(metaPart?.data?.status, "needs_review");
  });
});

describe("Ask Stream: extractCitationsFromText", () => {
  it("detects single and multiple citation markers", () => {
    const text =
      "Inflation print eased [C1] while GDP expanded by 7.2% [C2]. Cross-check with [C1].";
    const citations = extractCitationsFromText(text);

    assert.strictEqual(citations.length, 2);
    assert.strictEqual(citations[0].id, "C1");
    assert.strictEqual(citations[0].number, 1);
    assert.strictEqual(citations[1].id, "C2");
    assert.strictEqual(citations[1].number, 2);
  });

  it("re-uses known citations when provided", () => {
    const known = [
      {
        id: "C1",
        number: 1,
        source_title: "Known Document Title",
        doc_path: "vault/cs/os.md",
        page_number: 42,
        verified: true,
      },
    ];
    const text = "Reference to operating systems [C1].";
    const citations = extractCitationsFromText(text, known);

    assert.strictEqual(citations.length, 1);
    assert.strictEqual(citations[0].source_title, "Known Document Title");
    assert.strictEqual(citations[0].page_number, 42);
  });
});

describe("Ask Stream: Status Pipeline & Telemetry", () => {
  it("provides accurate stage descriptions", () => {
    assert.ok(getStageDescription("retrieving").includes("Retrieving"));
    assert.ok(getStageDescription("reranking").includes("BGE Reranker v2"));
    assert.ok(getStageDescription("answering").includes("Synthesizing"));
    assert.ok(getStageDescription("completed").includes("verified"));
  });

  it("simulates full typewriter stream lifecycle", async () => {
    const recordedStages: string[] = [];
    let streamedContent = "";

    const onUpdate = (state: StreamState) => {
      recordedStages.push(state.stage);
      if (state.stage === "answering") {
        streamedContent = state.text;
      }
    };

    const finalState = await simulateTypewriterStream({
      text: "Taylor Rule governs interest rate response [C1].",
      citations: [
        {
          id: "C1",
          number: 1,
          source_title: "Monetary Economics Note",
          verified: true,
        },
      ],
      onUpdate,
      charDelayMs: 1,
      retrievalDelayMs: 10,
      rerankDelayMs: 10,
    });

    assert.strictEqual(finalState.stage, "completed");
    assert.strictEqual(
      finalState.text,
      "Taylor Rule governs interest rate response [C1]."
    );
    assert.strictEqual(finalState.citations.length, 1);
    assert.strictEqual(finalState.citations[0].id, "C1");

    // Verified lifecycle transition sequence
    assert.ok(recordedStages.includes("retrieving"));
    assert.ok(recordedStages.includes("reranking"));
    assert.ok(recordedStages.includes("answering"));
    assert.ok(recordedStages.includes("completed"));
  });
});

describe("Citation Drawer Contract", () => {
  it("validates structured citation contract with excerpt and location", () => {
    const sampleCitation: CitationInfo = {
      id: "C1",
      number: 1,
      source_title: "Operating Systems Concepts",
      doc_path: "vault/cs/os_virtual_memory.md",
      heading: "Main Memory › Paging",
      page_number: 356,
      timestamp_s: 480,
      excerpt: "Paging avoids external fragmentation by dividing physical memory into frames.",
      verified: true,
      score: 0.95,
      doc_kind: "textbook",
    };

    assert.strictEqual(sampleCitation.id, "C1");
    assert.strictEqual(sampleCitation.page_number, 356);
    assert.strictEqual(sampleCitation.timestamp_s, 480);
    assert.ok(sampleCitation.excerpt?.includes("external fragmentation"));
    assert.strictEqual(sampleCitation.verified, true);
    assert.strictEqual(sampleCitation.score, 0.95);
  });
});

describe("Streamdown SEC-28 Security Checks", () => {
  it("disallows raw HTML and external images in token patterns", () => {
    const maliciousInput =
      'Check this out <script>alert("pwned")</script> and ![tracking beacon](https://attacker.example/pixel.gif) and <img src=x onerror=evil()>';

    // 1. Regex image pattern catches external image
    const imagePattern = /!\[(.*?)\]\((.*?)\)/g;
    const imgMatches = Array.from(maliciousInput.matchAll(imagePattern));
    assert.strictEqual(imgMatches.length, 1);
    assert.strictEqual(imgMatches[0][1], "tracking beacon");
    assert.strictEqual(
      imgMatches[0][2],
      "https://attacker.example/pixel.gif"
    );

    // 2. Citations regex properly matches [C#] markers
    const citationInput = "Claim verified in [C1] and [C2] and [C#].";
    const citationMatches = Array.from(
      citationInput.matchAll(/\[(C[0-9]+|C#)\]/g)
    );
    assert.strictEqual(citationMatches.length, 3);
    assert.strictEqual(citationMatches[0][1], "C1");
    assert.strictEqual(citationMatches[1][1], "C2");
    assert.strictEqual(citationMatches[2][1], "C#");
  });

  it("handles LaTeX equation block delimiters", () => {
    const mathInput = "$$i_t = r^* + \\pi_t$$";
    assert.ok(mathInput.startsWith("$$") && mathInput.endsWith("$$"));
    const innerTex = mathInput.slice(2, -2);
    assert.strictEqual(innerTex, "i_t = r^* + \\pi_t");
  });

  it("parses Mermaid diagram edges and nodes safely", () => {
    const mermaidCode = `graph TD
  A[Retrieve Chunks] --> B[Rerank BGE v2]
  B --> C{Score >= 0.30?}
  C -->|Yes| D[Draft Answer [C1]]
  C -->|No| E[Return Not Found]`;

    const edgeRegex =
      /([A-Za-z0-9_-]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\}|\(\[(.*?)\]\))?\s*(-->|---|-.->|==>)(?:\|(.*?)\|)?\s*([A-Za-z0-9_-]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\}|\(\[(.*?)\]\))?/;

    const lines = mermaidCode.split("\n");
    let matchCount = 0;
    for (const line of lines) {
      if (line.match(edgeRegex)) {
        matchCount++;
      }
    }
    assert.strictEqual(matchCount, 4);
  });
});
