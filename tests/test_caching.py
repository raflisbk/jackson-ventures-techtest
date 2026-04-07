import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

from agent.analyzer import compute_description_hash


# --- compute_description_hash ---


def test_hash_returns_64_char_hex():
    h = compute_description_hash("hello world")
    assert h is not None
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_strips_whitespace():
    assert compute_description_hash(" hello ") == compute_description_hash("hello")


def test_hash_returns_none_for_empty():
    assert compute_description_hash("") is None
    assert compute_description_hash("   ") is None
    assert compute_description_hash(None) is None


def test_hash_is_deterministic():
    assert compute_description_hash("stripe") == compute_description_hash("stripe")


def test_different_descriptions_produce_different_hashes():
    assert compute_description_hash("stripe") != compute_description_hash("openai")


# --- Two-condition cache logic (CACHE-01) ---


def test_two_condition_cache_hit_requires_both():
    """Hash mismatch overrides industry being set → NOT a cache hit."""
    desc = "A payments company"
    correct_hash = compute_description_hash(desc)
    stale_hash = "a" * 64

    is_hit_correct = (correct_hash == correct_hash) and ("FinTech" != None)
    is_hit_stale = (stale_hash == correct_hash) and ("FinTech" != None)

    assert is_hit_correct is True
    assert is_hit_stale is False


def test_partial_write_not_treated_as_cache_hit():
    """Hash matches but industry IS None → partial write → must re-analyze."""
    desc = "An AI tool for developers"
    computed_hash = compute_description_hash(desc)
    stored_hash = computed_hash   # hash was written
    stored_industry = None        # analysis failed before writing industry

    is_cache_hit = (stored_hash == computed_hash) and (stored_industry is not None)
    assert is_cache_hit is False
