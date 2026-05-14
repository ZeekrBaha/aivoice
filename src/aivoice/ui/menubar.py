from __future__ import annotations

import asyncio
import logging
import threading

from AppKit import NSBundle
import rumps

# Dev-mode fallback: set LSUIElement so the menu bar icon shows when running
# via `uv run aivoice`. In a proper .app bundle this comes from Info.plist.
NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"

from aivoice.config import Settings
from aivoice.pipeline.audio import AudioCapture
from aivoice.pipeline.cleanup.base import LLMCleaner
from aivoice.pipeline.cleanup.ollama_cleaner import OllamaCleaner
from aivoice.pipeline.cleanup.openai_cleaner import OpenAICleaner
from aivoice.pipeline.inject import ClipboardInjector
from aivoice.pipeline.orchestrator import Orchestrator
from aivoice.pipeline.stt.cloud_groq import CloudGroqEngine
from aivoice.pipeline.stt.local_mlx import LocalMLXEngine
from aivoice.pipeline.vad import VAD
from aivoice.ui.hotkey import HoldHotkey
from aivoice.utils.perms import check_all
from aivoice.version import __version__

log = logging.getLogger(__name__)

IDLE = "🎙"
LISTENING = "🔴"
WORKING = "⚙️"
ERROR = "⚠️"


class AivoiceApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("aivoice", title=IDLE, quit_button="Quit")
        self.settings = Settings.load()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orch: Orchestrator | None = None
        self._hotkey: HoldHotkey | None = None

        self.menu = [
            rumps.MenuItem(f"aivoice {__version__}"),
            None,
            rumps.MenuItem(f"Hotkey: ⌥ (hold)"),
            rumps.MenuItem(f"Engine: {self.settings.stt_engine}"),
            rumps.MenuItem(f"Cleanup: {'on (ollama)' if self.settings.cleanup_enabled else 'off'}"),
            None,
        ]

        # Start async pipeline in background thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ #
    # Async pipeline                                                       #
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_main())

    async def _async_main(self) -> None:
        # Permission gate — warn in menu if not trusted
        perms = check_all()
        if not perms.all_ok:
            log.warning("Missing permissions: %s", perms)
            self.title = ERROR
            log.error(
                "Grant Accessibility + Input Monitoring in "
                "System Settings → Privacy & Security, then restart aivoice"
            )
            return

        # Build STT engine
        if self.settings.stt_engine == "local_mlx":
            stt = LocalMLXEngine(self.settings.local_mlx_model)
        else:
            stt = CloudGroqEngine(self.settings.cloud_groq_model)

        log.info("warming up STT engine (%s)…", self.settings.stt_engine)
        await stt.warmup()
        log.info("STT engine ready")

        # Build optional cleaner
        cleaner: LLMCleaner | None = None
        if self.settings.cleanup_enabled:
            if self.settings.cleanup_engine == "ollama":
                cleaner = OllamaCleaner(self.settings.ollama_cleanup_model)
            else:
                cleaner = OpenAICleaner(self.settings.openai_cleanup_model)

        self._orch = Orchestrator(
            audio=AudioCapture(),
            vad=VAD(),
            stt=stt,
            cleaner=cleaner,
            injector=ClipboardInjector(paste=True),
            mode=self.settings.mode,
            vocabulary=self.settings.vocabulary,
        )

        self._hotkey = HoldHotkey(self.settings.hotkey, self._on_press, self._on_release)
        self._hotkey.start()
        log.info("aivoice ready — hold ⌥ to dictate")

        # Hold the event loop open
        while True:
            await asyncio.sleep(3600)

    async def _on_press(self) -> None:
        self.title = LISTENING
        try:
            await self._orch.on_press()
        except Exception:
            log.exception("on_press failed")
            self.title = IDLE

    async def _on_release(self) -> None:
        self.title = WORKING
        try:
            await self._orch.on_release()
        except Exception:
            log.exception("on_release failed")
        finally:
            self.title = IDLE


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    AivoiceApp().run()
