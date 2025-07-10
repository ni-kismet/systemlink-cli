"""Entry point for the SystemLink CLI application."""

import os
import sys

# PyInstaller workaround for package imports
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slcli.main import cli

if __name__ == "__main__":
    cli()
