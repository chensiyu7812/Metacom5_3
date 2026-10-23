from pathlib import Path

import pytest

from metacom_pm.paper1.llama_tokenizer import (
    LLAMA_TOKENIZER_JSON_SHA256,
    build_llama_token_counter,
    load_llama_tokenizer,
)

TOKENIZER_PATH = Path("/home/chenzhi/paper1_runs/frozen_tokenizers/llama31_8b_instruct_tokenizer.json")

pytest.importorskip("tokenizers")
if not TOKENIZER_PATH.exists():
    pytest.skip(f"frozen tokenizer not present at {TOKENIZER_PATH}", allow_module_level=True)


def test_load_llama_tokenizer_rejects_hash_mismatch(tmp_path):
    bad_path = tmp_path / "not_the_real_tokenizer.json"
    bad_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_llama_tokenizer(bad_path)


def test_load_llama_tokenizer_accepts_the_real_hash_verified_file():
    tokenizer = load_llama_tokenizer(TOKENIZER_PATH)
    ids = tokenizer.encode("hello world", add_special_tokens=False).ids
    assert len(ids) > 0


def test_build_llama_token_counter_counts_real_tokens_not_words():
    counter = build_llama_token_counter(TOKENIZER_PATH)
    # A real subword tokenizer count, not a whitespace word count -- these
    # must differ for genuinely multi-token words.
    text = "Profile fact [health_condition]: I am unable to sleep for 6 months now."
    word_count = len(text.split())
    token_count = counter(text)
    assert token_count != word_count
    assert token_count > 0


def test_build_llama_token_counter_is_deterministic():
    counter = build_llama_token_counter(TOKENIZER_PATH)
    a = counter("consistent token count check")
    b = counter("consistent token count check")
    assert a == b


def test_frozen_identity_constant_matches_the_real_file_hash():
    import hashlib

    digest = hashlib.sha256()
    with TOKENIZER_PATH.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    assert digest.hexdigest() == LLAMA_TOKENIZER_JSON_SHA256
