"""Entry point for the packaged app. Double-clicking the built .exe runs this.

It starts the local companion server, which auto-detects your League game and shows the
coaching note in your browser. No arguments, no setup.
"""
from coach.serve import main

if __name__ == "__main__":
    main()
