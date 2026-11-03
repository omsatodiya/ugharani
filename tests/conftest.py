import pytest

from ugharani import speech


@pytest.fixture(autouse=True)
def no_bundled_clips(tmp_path, monkeypatch):
    """Tests use fake Timbre audio; keep the real clips shipped in ugharani/clips/ out of the way."""
    monkeypatch.setattr(speech, "BUNDLED_DIR", tmp_path / "no-bundled-clips")


@pytest.fixture(autouse=True)
def fresh_gemini_order(monkeypatch):
    """llm remembers which model answered last; every test starts without that memory."""
    from ugharani import llm
    monkeypatch.setattr(llm, "_last_winner", None)
