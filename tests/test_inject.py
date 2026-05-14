import pytest

from aivoice.pipeline.inject import ClipboardInjector


@pytest.mark.asyncio
async def test_clipboard_round_trip():
    inj = ClipboardInjector(paste=False)
    await inj.inject("hello from test")
    assert inj.last_set == "hello from test"


@pytest.mark.asyncio
async def test_empty_string_is_noop():
    inj = ClipboardInjector(paste=False)
    await inj.inject("")
    assert inj.last_set is None
