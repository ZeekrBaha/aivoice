import fcntl
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from aivoice.version import __version__

load_dotenv()

_LOCK_FILE = None


def _lock_path() -> Path:
    override = os.environ.get("AIVOICE_LOCK_PATH")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "aivoice" / "aivoice.lock"


def _acquire_single_instance_lock() -> bool:
    global _LOCK_FILE
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return False
    lock_file.write(str(os.getpid()))
    lock_file.truncate()
    lock_file.flush()
    _LOCK_FILE = lock_file
    return True


def main() -> int:
    if "--version" in sys.argv:
        print(f"aivoice {__version__}")
        return 0
    if not _acquire_single_instance_lock():
        return 0
    from aivoice.ui.menubar import main as ui_main
    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
