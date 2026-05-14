import sys

from dotenv import load_dotenv

from aivoice.version import __version__

load_dotenv()


def main() -> int:
    if "--version" in sys.argv:
        print(f"aivoice {__version__}")
        return 0
    from aivoice.ui.menubar import main as ui_main
    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
