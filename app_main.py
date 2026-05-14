"""Entry point for py2app bundle — mirrors __main__.py without the CLI flags."""
from dotenv import load_dotenv

load_dotenv()

from aivoice.ui.menubar import main

main()
