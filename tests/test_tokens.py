import pytest

from hiivmind_corpus_lib import embeddings as emb
from hiivmind_corpus_lib.tokens import TokenMethod, count_tokens
from support import needs, open_corpus

REPO_DIR = "models--qdrant--bge-small-en-v1.5-onnx-q"


class Fixed:
    def count(self, text):
        return 7


def test_empty_text_is_zero():  # TOK-1; ports test_token_utils.py::test_empty_string_returns_zero
    assert count_tokens("") == 0


def test_whitespace_only_text_is_zero():  # TOK-1; ports test_whitespace_only_returns_zero
    assert count_tokens("   \n\t  ") == 0


def test_words_times_one_point_three_rounded_up():  # TOK-1
    assert count_tokens("Window functions over partitions") == 6   # ceil(4 x 1.3 = 5.2)
    assert count_tokens("a") == 2                                   # ceil(1.3)
    assert count_tokens(" ".join(["w"] * 10)) == 13                 # 10 x 1.3 is exactly 13, not 14
    assert count_tokens(" ".join(["w"] * 384)) == 500               # ceil(499.2), as previews pins


def test_the_count_is_an_int_and_grows_with_length():  # ports test_returns_integer, test_approximation_scales_with_length
    short, long = count_tokens("one two three"), count_tokens("one two three four five six seven eight nine ten")
    assert isinstance(short, int) and long > short


def test_a_tokenizer_gives_the_count_and_is_not_asked_about_empty_text():  # TOK-2
    assert count_tokens("anything at all", Fixed()) == 7
    assert count_tokens("  ", Fixed()) == 0


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed"))
    monkeypatch.setattr(emb, "find_spec", lambda name: object())   # fastembed is not a dev dependency
    return open_corpus(tmp_path)


def _cache_model(tmp_path, tokenizer=True, model=True):
    from tokenizers import Tokenizer as Hf, models, pre_tokenizers

    snap = tmp_path / "fastembed" / REPO_DIR / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    if model:
        (snap / "model_optimized.onnx").write_bytes(b"x")
    if tokenizer:
        hf = Hf(models.WordLevel({"[UNK]": 0, "alpha": 1, "beta": 2}, unk_token="[UNK]"))
        hf.pre_tokenizer = pre_tokenizers.Whitespace()
        hf.save(str(snap / "tokenizer.json"))


def test_without_a_cached_model_the_corpus_counts_words_and_creates_nothing(corpus, tmp_path):  # TOK-2
    assert corpus.tokens.method == TokenMethod.WORDS and corpus.tokens.tokenizer is None
    assert corpus.tokens.count("Window functions over partitions") == 6
    assert not (tmp_path / "fastembed").exists()


@needs("tokenizers")
def test_with_the_model_cached_the_corpus_counts_with_its_tokenizer(corpus, tmp_path):  # TOK-2
    _cache_model(tmp_path)
    assert corpus.tokens.method == TokenMethod.TOKENIZER
    assert corpus.tokens.count("alpha beta alpha gamma") == 4        # gamma is [UNK], still one token
    assert count_tokens("alpha beta", corpus.tokens.tokenizer) == 2


@needs("tokenizers")
def test_a_cached_model_without_a_tokenizer_file_counts_words(corpus, tmp_path):  # TOK-2
    _cache_model(tmp_path, tokenizer=False)
    assert corpus.tokens.method == TokenMethod.WORDS


@needs("tokenizers")
def test_a_cached_tokenizer_without_the_cached_model_counts_words(corpus, tmp_path):  # TOK-2: the tokenizer is the model's, so the model must be cached too
    _cache_model(tmp_path, model=False)
    assert corpus.tokens.method == TokenMethod.WORDS


@needs("tokenizers")
def test_without_the_extra_the_corpus_counts_words_even_when_cached(corpus, tmp_path, monkeypatch):  # TOK-2
    _cache_model(tmp_path)
    monkeypatch.setattr(emb, "find_spec", lambda name: None)
    assert corpus.tokens.method == TokenMethod.WORDS
