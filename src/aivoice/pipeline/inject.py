from __future__ import annotations

import asyncio


class ClipboardInjector:
    def __init__(self, paste: bool = True, restore_delay: float = 0.2) -> None:
        self.paste = paste
        self.restore_delay = restore_delay
        self.last_set: str | None = None

    def _read_clipboard(self) -> str:
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        return pb.stringForType_(NSStringPboardType) or ""

    def _write_clipboard(self, text: str) -> None:
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSStringPboardType)

    def _post_cmd_v(self) -> None:
        from pynput.keyboard import Controller, Key
        kb = Controller()
        with kb.pressed(Key.cmd):
            kb.press("v")
            kb.release("v")

    async def inject(self, text: str) -> None:
        if not text:
            return
        self.last_set = text
        previous = self._read_clipboard() if self.paste else ""
        self._write_clipboard(text)
        if not self.paste:
            return
        await asyncio.sleep(0.05)
        self._post_cmd_v()
        await asyncio.sleep(self.restore_delay)
        # Only restore if clipboard still has our text (user didn't copy something else)
        if self._read_clipboard() == text and previous:
            self._write_clipboard(previous)
