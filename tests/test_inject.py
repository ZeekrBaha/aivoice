import pytest

from aivoice.pipeline.inject import ClipboardInjector


@pytest.mark.asyncio
async def test_clipboard_round_trip(monkeypatch):
    clipboard = {"value": ""}
    inj = ClipboardInjector(paste=False)
    monkeypatch.setattr(inj, "_read_clipboard", lambda: clipboard["value"])
    monkeypatch.setattr(inj, "_write_clipboard", lambda text: clipboard.update(value=text))

    await inj.inject("clipboard sample text")

    assert inj.last_set == "clipboard sample text"
    assert clipboard["value"] == "clipboard sample text"


@pytest.mark.asyncio
async def test_empty_string_is_noop():
    inj = ClipboardInjector(paste=False)
    await inj.inject("")
    assert inj.last_set is None
