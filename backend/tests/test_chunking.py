import pytest

from app.services.chunking import chunk_text


def test_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n ") == []


def test_short_single_chunk():
    assert chunk_text("hello world", 100, 10) == ["hello world"]


def test_chunks_within_size():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(30))
    chunks = chunk_text(text, 300, 50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_overlap_between_consecutive_chunks():
    text = " ".join(f"w{i}" for i in range(2000))
    chunks = chunk_text(text, 200, 50)
    assert len(chunks) > 2
    for a, b in zip(chunks, chunks[1:]):
        tail = a[-20:].strip()
        assert tail in b


def test_unbroken_string_terminates_and_covers():
    import random

    rnd = random.Random(0)
    text = "".join(rnd.choice("abcdefghij") for _ in range(5000))
    chunks = chunk_text(text, 1000, 200)
    assert all(len(c) <= 1000 for c in chunks)
    assert chunks[0].startswith(text[:50])
    assert chunks[-1].endswith(text[-50:])
    # every character position is covered by some chunk, in order with overlap
    pos = 0
    for c in chunks:
        idx = text.find(c, max(0, pos - 1000))
        assert idx != -1 and idx <= pos
        pos = idx + len(c)
    assert pos == len(text)


def test_no_overlap_unbroken_exact():
    text = "x" * 5000
    chunks = chunk_text(text, 1000, 0)
    assert "".join(chunks) == text


def test_no_mid_codepoint_split():
    text = "😀é漢" * 1500
    chunks = chunk_text(text, 100, 20)
    for c in chunks:
        c.encode("utf-8")  # raises on lone surrogates
        assert all(ch in "😀é漢" for ch in c)


@pytest.mark.parametrize("size,overlap", [(100, 100), (100, 150), (100, -1), (0, 0)])
def test_invalid_params(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("abc", size, overlap)


def test_content_preserved_with_paragraphs():
    paras = [f"Para {i} " + "z" * 80 for i in range(20)]
    chunks = chunk_text("\n\n".join(paras), 250, 40)
    joined = "\n".join(chunks)
    for p in paras:
        assert p in joined
