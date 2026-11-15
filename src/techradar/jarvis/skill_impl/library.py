from __future__ import annotations


def speak_library_summary(book_title: str, chapter_title: str, key_idea: str) -> str:
    """Produce spoken text summarizing a library book chapter."""
    b_clean = book_title.strip()
    c_clean = chapter_title.strip()
    k_clean = key_idea.strip()

    if not b_clean and not c_clean:
        return f"Key idea: {k_clean}" if k_clean else "No summary available."

    if b_clean and c_clean:
        return f"From '{b_clean}', chapter '{c_clean}': {k_clean}"
    elif b_clean:
        return f"From '{b_clean}': {k_clean}"
    else:
        return f"From chapter '{c_clean}': {k_clean}"
