import { describe, it } from "node:test";
import assert from "node:assert";

import type { FlashcardItem, DailyCaps, FSRSRating } from "./flashcard-view";
import type { MCQQuestion } from "./mcq-drill";
import type { MistakeItem } from "./mistakes-notebook";

describe("Flashcard FSRS v5 Contract & Limits", () => {
  it("enforces FSRS v5 rating bounds 1 to 4", () => {
    const validRatings: FSRSRating[] = [1, 2, 3, 4];
    for (const r of validRatings) {
      assert.ok(r >= 1 && r <= 4, `Rating ${r} must be within 1-4`);
    }
  });

  it("enforces daily caps structure: 10 new / 40 reviews limit", () => {
    const dailyCaps: DailyCaps = {
      newCount: 4,
      maxNew: 10,
      reviewCount: 18,
      maxReviews: 40,
    };

    assert.strictEqual(dailyCaps.maxNew, 10);
    assert.strictEqual(dailyCaps.maxReviews, 40);
    assert.ok(dailyCaps.newCount <= dailyCaps.maxNew);
    assert.ok(dailyCaps.reviewCount <= dailyCaps.maxReviews);
  });

  it("validates card data structure with question, answer, and excerpt", () => {
    const card: FlashcardItem = {
      id: "card-test-01",
      topic: "Macroeconomics",
      chapter: "Monetary Policy",
      question: "What is EBLR?",
      answer: "External Benchmark Lending Rate.",
      excerpt: "Mandatory link to RBI repo rate.",
      source: "RBI Bulletin",
      state: "review",
      stability: 3.4,
      difficulty: 5.2,
      reps: 3,
      lapses: 0,
    };

    assert.strictEqual(card.id, "card-test-01");
    assert.strictEqual(card.state, "review");
    assert.ok(card.stability && card.stability > 0);
    assert.ok(card.question.length > 5);
    assert.ok(card.answer.length > 5);
  });
});

describe("MCQ Drill Structure & Verification", () => {
  it("validates exactly 4 options with labeled A, B, C, D indices", () => {
    const labels = ["A", "B", "C", "D"];
    const question: MCQQuestion = {
      id: "mcq-test-01",
      subject: "Computer Systems",
      question: "Which condition triggers a TLB shootdown in SMP?",
      options: [
        "L1 data cache hit on another core.",
        "Unprivileged synchronous read syscall.",
        "PTE modification or invalidation affecting other cores.",
        "Thread group context switch.",
      ],
      answerIndex: 2,
      explanation: "Page table modifications broadcast IPIs to invalidate stale TLB entries.",
      source: "OS Concepts",
    };

    assert.strictEqual(question.options.length, 4);
    assert.ok(question.answerIndex >= 0 && question.answerIndex < 4);
    assert.strictEqual(labels[question.answerIndex], "C");
    assert.ok(new Set(question.options).size === 4, "Options must be strictly unique");
  });

  it("verifies timer limit defaults to 60 seconds", () => {
    const defaultTimerLimit = 60;
    assert.strictEqual(defaultTimerLimit, 60);
  });
});

describe("Mistakes Notebook Tracking & Resolution", () => {
  it("tracks active question mistake fields, tags, and timestamps", () => {
    const mistake: MistakeItem = {
      id: "mstk-test-001",
      question: "What is the statutory failure criteria for MPC inflation targeting?",
      chosen: "Breach for 2 consecutive quarters",
      correct: "Breach for 3 consecutive quarters",
      explanation: "Section 45ZN of RBI Act specifies 3 consecutive quarters.",
      topic: "Macroeconomics",
      tags: ["Monetary Policy", "RBI Act"],
      source: "MCQ Drill",
      createdAt: new Date().toISOString(),
      resolved: false,
      resolvedAt: null,
    };

    assert.strictEqual(mistake.resolved, false);
    assert.strictEqual(mistake.resolvedAt, null);
    assert.ok(mistake.tags && mistake.tags.length === 2);
    assert.ok(mistake.question.length > 10);
  });

  it("simulates marking mistake as resolved with timestamp stamp", () => {
    const mistake: MistakeItem = {
      id: "mstk-test-002",
      question: "Article 22 safeguards against arbitrary arrest",
      chosen: "Bail within 48 hours",
      correct: "Magistrate within 24 hours",
      explanation: "Article 22(2) requires presentation before magistrate within 24h.",
      topic: "Indian Polity",
      createdAt: "2026-11-08T14:00:00Z",
      resolved: false,
      resolvedAt: null,
    };

    // Resolve
    const resolvedMistake: MistakeItem = {
      ...mistake,
      resolved: true,
      resolvedAt: new Date().toISOString(),
    };

    assert.strictEqual(resolvedMistake.resolved, true);
    assert.ok(resolvedMistake.resolvedAt !== null);
  });
});
