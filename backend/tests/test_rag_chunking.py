from app.rag.chunking import chunk_document


def test_chunks_one_section_per_heading_when_sections_are_short():
    text = "# Title\n\n## First\nShort body one.\n\n## Second\nShort body two.\n"
    chunks = chunk_document("doc.md", text, chunk_size=500, chunk_overlap=50)
    sections = [c.section_reference for c in chunks]
    assert sections == ["First", "Second"]
    assert chunks[0].text == "Short body one."
    assert chunks[1].text == "Short body two."


def test_content_before_first_heading_becomes_introduction():
    text = "Some preamble text.\n\n## Real Section\nBody.\n"
    chunks = chunk_document("doc.md", text, chunk_size=500, chunk_overlap=50)
    assert chunks[0].section_reference == "Introduction"
    assert chunks[0].text == "Some preamble text."


def test_document_with_no_headings_is_a_single_chunk():
    text = "Just a plain paragraph with no markdown headings at all."
    chunks = chunk_document("doc.md", text, chunk_size=500, chunk_overlap=50)
    assert len(chunks) == 1
    assert chunks[0].section_reference == "Document"
    assert chunks[0].text == text


def test_empty_document_produces_no_chunks():
    assert chunk_document("doc.md", "", chunk_size=500, chunk_overlap=50) == []
    assert chunk_document("doc.md", "   \n\n  ", chunk_size=500, chunk_overlap=50) == []


def test_long_section_is_split_with_a_sliding_window():
    body = "0123456789" * 100  # 1000 distinct-ish chars
    text = f"## Long Section\n{body}\n"
    chunks = chunk_document("doc.md", text, chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1
    assert all(c.section_reference == "Long Section" for c in chunks)
    assert body.startswith(chunks[0].text[:20])
    assert body.endswith(chunks[-1].text[-20:])


def test_sliding_window_chunks_overlap():
    body = "0123456789" * 40  # 400 chars
    text = f"## Section\n{body}\n"
    chunks = chunk_document("doc.md", text, chunk_size=150, chunk_overlap=50)
    assert len(chunks) > 1
    # The tail of one chunk should reappear at the head of the next (the overlap).
    overlap_expected = chunks[0].text[-50:]
    assert chunks[1].text.startswith(overlap_expected)


def test_chunk_indices_are_sequential_across_the_whole_document():
    text = "## A\nBody A.\n\n## B\nBody B.\n\n## C\nBody C.\n"
    chunks = chunk_document("doc.md", text, chunk_size=500, chunk_overlap=50)
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chunk_size_and_overlap_are_explicit_parameters_not_hardcoded():
    """US-29 DoD: chunk size and overlap are configurable — proven here by
    the fact that changing these arguments changes the chunking outcome."""
    body = "word " * 200  # 1000 chars
    text = f"## Section\n{body}\n"
    small = chunk_document("doc.md", text, chunk_size=200, chunk_overlap=20)
    large = chunk_document("doc.md", text, chunk_size=800, chunk_overlap=20)
    assert len(small) > len(large)
