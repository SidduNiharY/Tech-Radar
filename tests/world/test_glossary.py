"""Tests for techradar.world.glossary."""

from techradar.world.glossary import BASELINE_TERMS, GlossaryTerm, WorldGlossary


def test_baseline_terms_loaded() -> None:
    glossary = WorldGlossary()
    expected_baselines = {
        "Repo Rate",
        "GDP",
        "Inflation",
        "Fiscal Deficit",
        "RAG",
        "Transformer",
        "eBPF",
    }
    loaded_names = {t.term for t in glossary.terms.values()}
    assert expected_baselines.issubset(loaded_names)
    assert len(BASELINE_TERMS) == 7


def test_add_and_lookup_case_insensitive() -> None:
    glossary = WorldGlossary(load_baselines=False)
    term = GlossaryTerm(
        term="Quantum Computing",
        category="Technology",
        definition="Computation using quantum mechanics principles.",
        synonyms=["quantum tech", "QC"],
    )
    glossary.add_term(term)

    # Exact lookup
    assert glossary.lookup("Quantum Computing") is not None
    assert glossary.lookup("Quantum Computing").term == "Quantum Computing"

    # Lowercase lookup
    assert glossary.lookup("quantum computing") is not None
    assert glossary.lookup("quantum computing").term == "Quantum Computing"

    # Uppercase lookup
    assert glossary.lookup("QUANTUM COMPUTING") is not None

    # Lookup by synonym
    assert glossary.lookup("quantum tech") is not None
    assert glossary.lookup("quantum tech").term == "Quantum Computing"
    assert glossary.lookup("QC") is not None
    assert glossary.lookup("qc").term == "Quantum Computing"

    # Non-existent and empty lookups
    assert glossary.lookup("NonExistent") is None
    assert glossary.lookup("") is None
    assert glossary.lookup("   ") is None


def test_search_queries() -> None:
    glossary = WorldGlossary()

    # Search by exact term
    results_gdp = glossary.search("GDP")
    assert len(results_gdp) > 0
    assert results_gdp[0].term == "GDP"

    # Search by substring in term name
    results_rate = glossary.search("rate")
    assert any(t.term == "Repo Rate" for t in results_rate)

    # Search by synonym
    results_syn = glossary.search("Gross Domestic Product")
    assert any(t.term == "GDP" for t in results_syn)

    # Search by definition word
    results_def = glossary.search("kernel")
    assert any(t.term == "eBPF" for t in results_def)

    # Search by category
    results_econ = glossary.search("Economy")
    econ_terms = {t.term for t in results_econ}
    assert {"Repo Rate", "GDP", "Inflation", "Fiscal Deficit"}.issubset(econ_terms)

    # Search empty or not found
    assert glossary.search("") == []
    assert glossary.search("   ") == []
    assert glossary.search("xyznonexistentterm12345") == []


def test_link_terms_in_markdown_unlinked_and_canonical() -> None:
    glossary = WorldGlossary()
    text = "The repo rate and GDP are key indicators."
    linked = glossary.link_terms_in_markdown(text)
    assert linked == "The [[Repo Rate]] and [[GDP]] are key indicators."


def test_link_terms_in_markdown_no_double_linking() -> None:
    glossary = WorldGlossary()
    text = "Already linked: [[Inflation]] and [[GDP]]. Unlinked: Inflation and GDP."
    linked = glossary.link_terms_in_markdown(text)
    expected = "Already linked: [[Inflation]] and [[GDP]]. Unlinked: [[Inflation]] and [[GDP]]."
    assert linked == expected


def test_link_terms_preserves_code_and_hyperlinks() -> None:
    glossary = WorldGlossary()
    text = (
        "Check `Transformer` code and [GDP Link](https://example.com/gdp). "
        "Also Transformer and GDP in plain text."
    )
    linked = glossary.link_terms_in_markdown(text)
    expected = (
        "Check `Transformer` code and [GDP Link](https://example.com/gdp). "
        "Also [[Transformer]] and [[GDP]] in plain text."
    )
    assert linked == expected


def test_link_terms_empty_or_no_match() -> None:
    glossary = WorldGlossary()
    assert glossary.link_terms_in_markdown("") == ""
    assert glossary.link_terms_in_markdown("No glossary terms here.") == "No glossary terms here."

    empty_glossary = WorldGlossary(load_baselines=False)
    assert empty_glossary.link_terms_in_markdown("GDP and Inflation") == "GDP and Inflation"


def test_link_terms_longer_matches_first() -> None:
    glossary = WorldGlossary(load_baselines=False)
    glossary.add_term(
        GlossaryTerm(
            term="Fiscal Deficit",
            category="Economy",
            definition="Deficit",
        )
    )
    glossary.add_term(
        GlossaryTerm(
            term="Deficit",
            category="Economy",
            definition="General deficit",
        )
    )
    text = "Fiscal Deficit is worse than just a normal Deficit."
    linked = glossary.link_terms_in_markdown(text)
    assert linked == "[[Fiscal Deficit]] is worse than just a normal [[Deficit]]."
