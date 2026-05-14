import sys

from aivoice.version import __version__


def main() -> int:
    if "--version" in sys.argv:
        print(f"aivoice {__version__}")
        return 0
    print("aivoice: use --version (full UI lands in Task 17)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
