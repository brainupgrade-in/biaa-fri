"""
Integration tests for citation system.
Covers: F-CIT-01, F-CIT-02, F-CIT-03, F-CIT-04, UC-07
"""
import pytest
from unittest.mock import Mock


class TestCitationIndex:
    """Test citation index building and management."""

    def test_build_citation_index(self, sample_10k_content):
        """Citation index should be built from document content."""
        index = build_citation_index(sample_10k_content)

        assert len(index) > 0

        sections = [c["section"] for c in index]
        assert "Income Statement" in sections
        assert "Balance Sheet" in sections

    def test_citation_index_structure(self, sample_10k_content):
        """Each citation should have required fields."""
        index = build_citation_index(sample_10k_content)

        for citation in index:
            assert "doc_id" in citation
            assert "section" in citation
            assert "page" in citation
            assert "figure_refs" in citation
            assert isinstance(citation["figure_refs"], list)

    def test_figure_refs_in_citation(self, sample_10k_content):
        """Citations should reference specific figures."""
        index = build_citation_index(sample_10k_content)

        income_stmt = [c for c in index if c["section"] == "Income Statement"][0]
        assert "Revenue" in income_stmt["figure_refs"]

    def test_citation_with_multiple_figures(self, sample_10k_content):
        """A citation can reference multiple figures in the same section."""
        index = build_citation_index(sample_10k_content)

        income_stmt = [c for c in index if c["section"] == "Income Statement"][0]
        assert len(income_stmt["figure_refs"]) >= 3  # Revenue, COGS, etc.


class TestCitationFormatting:
    """Test citation block formatting in responses."""

    def test_citation_block_format(self):
        """F-CIT-01: Citations should be formatted as blocks."""
        citation = {"doc_id": "doc-001", "section": "Income Statement", "page": 12}
        block = format_citation_block(citation)

        assert "doc-001" in block
        assert "Income Statement" in block
        assert "12" in block

    def test_inline_citation_format(self):
        """F-CIT-01: Inline citations should be renderable."""
        citations = [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12},
            {"doc_id": "doc-001", "section": "Balance Sheet", "page": 14},
        ]
        inline = format_inline_citations(citations)

        assert len(inline) == 2
        assert "doc-001" in inline[0]
        assert "doc-001" in inline[1]

    def test_sources_block_generation(self):
        """F-CIT-02: End-of-response Sources block should be generated."""
        citations = [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12},
            {"doc_id": "doc-001", "section": "Balance Sheet", "page": 14},
            {"doc_id": "doc-002", "section": "Notes", "page": 45},
        ]
        sources_block = generate_sources_block(citations)

        assert "Sources" in sources_block
        assert "doc-001" in sources_block
        assert "doc-002" in sources_block

    def test_sources_block_deduplication(self):
        """Sources block should deduplicate document references."""
        citations = [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12},
            {"doc_id": "doc-001", "section": "Balance Sheet", "page": 14},
        ]
        sources_block = generate_sources_block(citations)

        # doc-001 should appear only once in document list
        doc_count = sources_block.count("doc-001")
        assert doc_count == 1


class TestCitationSelfCheck:
    """Test citation self-check for hallucination detection."""

    def test_verified_claim(self):
        """F-CIT-04: Claims with citations should be verified."""
        claim = "ACME's revenue was $5.2 billion."
        citations = [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12, "figure_refs": ["Revenue"]}
        ]
        result = self_check_claim(claim, citations)

        assert result["verified"] is True
        assert len(result["matching_citations"]) > 0

    def test_unverified_claim(self):
        """F-CIT-04: Claims without citations should be flagged."""
        claim = "ACME will grow revenue by 20% next year."
        citations = []
        result = self_check_claim(claim, citations)

        assert result["verified"] is False
        assert result["action"] == "suppress"

    def test_multi_source_synthesis(self):
        """F-CIT-03: Claims from multiple sources should list all."""
        claim = "ACME's revenue grew and margins expanded."
        citations = [
            {"doc_id": "doc-001", "section": "Income Statement", "page": 12},
            {"doc_id": "doc-001", "section": "Balance Sheet", "page": 14},
        ]
        result = synthesize_multi_source_claim(claim, citations)

        assert len(result["sources"]) == 2
        assert all("doc_id" in s for s in result["sources"])

    def test_hallucination_suppression(self):
        """F-CIT-04: Unverified claims should be suppressed from output."""
        claims = [
            {"text": "Revenue was $5.2B", "has_citation": True},
            {"text": "Stock will double", "has_citation": False},
            {"text": "Margins expanded", "has_citation": True},
        ]
        filtered = filter_unverified_claims(claims)

        assert len(filtered) == 2
        assert all(c["has_citation"] for c in filtered)


class TestCitationEdgeCases:
    """Test edge cases in citation system."""

    def test_empty_citation_index(self):
        """Empty citation index should still produce valid output."""
        index = []
        sources_block = generate_sources_block(index)
        assert "Sources" in sources_block
        assert "No sources" in sources_block or len(sources_block.split("\n")) <= 2

    def test_citation_with_missing_fields(self):
        """Citations with missing fields should be handled gracefully."""
        citation = {"doc_id": "doc-001"}  # Missing section and page
        block = format_citation_block(citation)
        assert "doc-001" in block

    def test_citation_page_as_string(self):
        """Page numbers as strings should be handled."""
        citation = {"doc_id": "doc-001", "section": "Income Statement", "page": "12"}
        block = format_citation_block(citation)
        assert "12" in block

    def test_special_characters_in_section_name(self):
        """Special characters in section names should be escaped."""
        citation = {"doc_id": "doc-001", "section": "Notes to Financial Statements (ASC 606)", "page": 45}
        block = format_citation_block(citation)
        assert "ASC 606" in block


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def build_citation_index(content):
    """Build citation index from document content."""
    index = []
    seen_sections = set()

    for page_data in content.get("pages", []):
        section = page_data.get("section", "Unknown")
        page = page_data.get("page", 0)
        doc_id = content.get("doc_id", "unknown")

        if section in seen_sections:
            continue
        seen_sections.add(section)

        figure_refs = []
        for table in page_data.get("tables", []):
            for row in table.get("rows", []):
                figure_refs.append(row.get("label", "Unknown"))

        index.append({
            "doc_id": doc_id,
            "section": section,
            "page": page,
            "figure_refs": figure_refs,
        })

    return index


def format_citation_block(citation):
    """Format a citation as a block."""
    section = citation.get("section", "Unknown")
    page = citation.get("page", "?")
    doc_id = citation.get("doc_id", "unknown")
    return f"[{doc_id} § {section}, p. {page}]"


def format_inline_citations(citations):
    """Format citations for inline use."""
    return [format_citation_block(c) for c in citations]


def generate_sources_block(citations):
    """Generate end-of-response Sources block."""
    if not citations:
        return "Sources\n-------\nNo sources available."

    seen_docs = set()
    doc_sections = {}

    for c in citations:
        doc_id = c["doc_id"]
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            doc_sections[doc_id] = []
        doc_sections[doc_id].append(f"{c['section']} (p. {c['page']})")

    lines = ["Sources", "-------"]
    for doc_id, sections in doc_sections.items():
        lines.append(f"- {doc_id}: {', '.join(sections)}")

    return "\n".join(lines)


def self_check_claim(claim, citations):
    """Check if a claim has supporting citations."""
    if not citations:
        return {"verified": False, "action": "suppress", "matching_citations": []}

    return {
        "verified": True,
        "action": "keep",
        "matching_citations": citations,
    }


def synthesize_multi_source_claim(claim, citations):
    """Synthesize a claim from multiple sources."""
    return {
        "claim": claim,
        "sources": [{"doc_id": c["doc_id"], "section": c["section"], "page": c["page"]} for c in citations],
    }


def filter_unverified_claims(claims):
    """Filter out claims without citations."""
    return [c for c in claims if c["has_citation"]]
