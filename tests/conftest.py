import pytest


@pytest.fixture(autouse=True)
def _no_real_model_cache(tmp_path, monkeypatch):
    """Tests never see a machine's real fastembed cache: counts and states must not depend on it."""
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "no-fastembed-cache"))
