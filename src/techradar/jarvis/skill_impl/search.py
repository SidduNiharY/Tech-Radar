from __future__ import annotations


def speak_search_result(top_chunk: str) -> str:
    """Produce spoken text for the top search result chunk."""
    chunk_clean = top_chunk.strip()
    if not chunk_clean:
        return "I could not find any relevant information in your knowledge base."
    return f"Here is what I found: {chunk_clean}"
