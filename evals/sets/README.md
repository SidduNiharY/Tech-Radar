# Evaluation Sets for TechRadar Brain Models Benchmarking

This directory contains evaluation sets used to validate and benchmark local LLMs and SLMs across different roles (Worker, Checker, Embedding, and Exam Prep) before activating them in production.

## Purpose

Under SEC-23 and Phase 10 Model Admin guidelines:
- A model tag cannot be switched to an active role without passing the corresponding role evaluation threshold.
- The Worker role requires structured JSON generation and reliable tagging (`passes_worker`).
- The Checker role requires accurate error detection without false flags (`passes_checker`).
- Exam and knowledge roles require subject matter accuracy (e.g., GATE CS benchmarks).

## Dataset Schema

Each evaluation YAML file contains a list of test questions / items:

```yaml
version: 1
suite: "gate_cs"
description: "GATE Computer Science evaluation dataset"
items:
  - id: "gate-cs-001"
    subject: "Data Structures & Algorithms"
    topic: "Asymptotic Complexity"
    type: "mcq" # mcq | nat | json_extract | tagging
    question: "What is the worst-case time complexity of QuickSort with standard median-of-three partitioning?"
    options:
      A: "O(n log n)"
      B: "O(n^2)"
      C: "O(n)"
      D: "O(log n)"
    expected_answer: "B"
    explanation: "Worst-case occurs when partitions are highly unbalanced (e.g. sorted array), giving O(n^2)."
```

## Role Pass Criteria

1. **Worker Role (`passes_worker`):**
   - Tag Agreement $\ge 0.90$
   - First-try JSON Valid Syntax $\ge 0.98$
2. **Checker Role (`passes_checker`):**
   - Wrong Answer / Key Catch Rate $\ge 0.90$
   - False Flag Rate $\le 0.05$
3. **Embedding Role (`passes_embed`):**
   - Hit Rate @ 5 $\ge 0.80$
   - MRR $\ge 0.70$
4. **Night A/B Blind Evaluation (`passes_night`):**
   - Owner prefers candidate model in at least 2 out of 3 prompts.

## Files

- `gate_cs.example.yaml`: Sample evaluation suite for GATE Computer Science practice questions.
- Production evaluation sets (`tagging.yaml`, `json_extract.yaml`, `mcq_checker.yaml`) are git-ignored to prevent test data leakage.
