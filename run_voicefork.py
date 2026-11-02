"""Entry point for PyInstaller builds. Double-clicking the exe opens the app."""
import sys

from voicefork.cli import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["gui"])
