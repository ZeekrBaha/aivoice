from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from pynput import keyboard

OnPress = Callable[[], Awaitable[None]]
OnRelease = Callable[[], Awaitable[None]]

_KEY_MAP = {
    "alt": keyboard.Key.alt,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
    "cmd": keyboard.Key.cmd,
    "ctrl": keyboard.Key.ctrl,
    "shift": keyboard.Key.shift,
}


class HoldHotkey:
    """Fires on_press when the bound key goes down, on_release when it comes up.
    Re-entrant: repeated press events while held are ignored."""

    def __init__(self, key_name: str, on_press: OnPress, on_release: OnRelease) -> None:
        self.key = _KEY_MAP[key_name]
        self.on_press = on_press
        self.on_release = on_release
        self._held = False
        self._listener: keyboard.Listener | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _on_press(self, key) -> None:
        if key != self.key or self._held or self._loop is None:
            return
        self._held = True
        asyncio.run_coroutine_threadsafe(self.on_press(), self._loop)

    def _on_release(self, key) -> None:
        if key != self.key or not self._held or self._loop is None:
            return
        self._held = False
        asyncio.run_coroutine_threadsafe(self.on_release(), self._loop)

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
