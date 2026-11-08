# TechRadar Brain

TechRadar Brain is an autonomous, privacy-preserving, local-first learning system and personal AI second brain. Built to run primarily on personal hardware, it transforms daily reading, news consumption, exam preparation, and English language coaching into an interconnected knowledge base without generating recurring cloud LLM costs.

The system features an Intake Gateway that sanitizes all incoming documents, an isolated sandboxed parsing tier, vector-augmented retrieval (RAG) backed by PostgreSQL and pgvector, spaced-repetition active recall (FSRS), and a voice assistant named Jarvis. For architectural details, security controls (SEC-01 through SEC-68), and implementation specifications, see [05_Architecture.md](05_Architecture.md), the operational rules in [AGENTS.md](AGENTS.md), and the implementation roadmap in [docs/superpowers/plans/2026-11-07-techradar-00-overview.md](docs/superpowers/plans/2026-11-07-techradar-00-overview.md).
