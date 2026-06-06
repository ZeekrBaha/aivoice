import pytest

from aivoice.pipeline.inject import ClipboardInjector


@pytest.mark.asyncio
async def test_clipboard_round_trip():
    inj = ClipboardInjector(paste=False)
    await inj.inject("dictation fixture text")
    assert inj.last_set == "dictation fixture text"


@pytest.mark.asyncio
async def test_empty_string_is_noop():
    inj = ClipboardInjector(paste=False)
    await inj.inject("")
    assert inj.last_set is None
