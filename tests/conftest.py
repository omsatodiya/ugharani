import pytest

from ugharani import speech


@pytest.fixture(autouse=True)
def no_bundled_clips(tmp_path, monkeypatch):
    """Tests use fake Timbre audio; keep the real clips shipped in ugharani/clips/ out of the way."""
    monkeypatch.setattr(speech, "BUNDLED_DIR", tmp_path / "no-bundled-clips")
