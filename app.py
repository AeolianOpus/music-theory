"""
Music Theory Scale Finder — Main Application Entry Point
"""
# Bootstrap: patch venv and check environment before importing modules
import bootstrap
bootstrap.run_bootstrap()

import sys
import os

# Ensure the app can find its data when running as a PyInstaller bundle
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add base dir to path for relative imports
sys.path.insert(0, BASE_DIR)


def find_soundfont() -> str | None:
    """Look for a .sf2 file in the soundfonts directory."""
    sf_dir = os.path.join(BASE_DIR, "soundfonts")
    if not os.path.isdir(sf_dir):
        return None
    for f in os.listdir(sf_dir):
        if f.lower().endswith(".sf2"):
            return os.path.join(sf_dir, f)
    return None


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    app = QApplication(sys.argv)
    app.setApplicationName("Music Theory Scale Finder")
    app.setOrganizationName("MusicTheory")

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialize FluidSynth audio engine (fast path — always available)
    from core.audio_engine import AudioEngine
    audio = AudioEngine()
    sf_path = find_soundfont()
    if sf_path:
        audio.initialize(sf_path)
        print(f"Loaded SoundFont: {sf_path}")
    else:
        print("No SoundFont found in soundfonts/ — audio playback disabled.")
        print("See soundfonts/README.md for download instructions.")

    # Initialize DawDreamer VST engine (studio path — optional, may fail gracefully)
    # Loads Kontakt 8 with the 7 saved presets from presets/.
    # If dawdreamer isn't installed, Kontakt isn't found, or preset load
    # fails, daw stays None and the app falls back to FluidSynth-only.
    from core.dawdreamer_engine import DawDreamerEngine
    daw = DawDreamerEngine()
    try:
        if daw.initialize():
            print(f"DawDreamer ready — loaded presets: {daw.list_plugins()}")
        else:
            print("DawDreamer initialization returned False — VST backend disabled.")
            daw = None
    except Exception as e:
        print(f"DawDreamer failed to initialize ({e}) — VST backend disabled.")
        daw = None

    # Launch main window
    from gui.main_window import MainWindow
    window = MainWindow(audio_engine=audio, dawdreamer_engine=daw, base_dir=BASE_DIR)
    window.show()

    exit_code = app.exec()

    # Cleanup
    audio.shutdown()
    if daw is not None:
        daw.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
