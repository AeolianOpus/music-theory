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

    # Initialize DawDreamer VST engine (studio path — optional).
    # Construction is instant; initialize() blocks for ~30s loading Kontakt
    # and its 7 presets, so we run it on a background thread and let the
    # window open immediately. The engine notifies listeners when readiness
    # settles — MainWindow subscribes to update its status bar and enable
    # the VST backend selector.
    #
    # Note: daw is created here even if init might fail. It stays not-ready
    # (is_ready False) if dawdreamer/Kontakt is missing or throws; the GUI
    # treats not-ready as "VST offline" the same as if daw were None.
    import threading
    from core.dawdreamer_engine import DawDreamerEngine
    daw = DawDreamerEngine()

    def _init_daw_worker():
        try:
            if daw.initialize():
                print(f"DawDreamer ready — loaded presets: {daw.list_plugins()}")
            else:
                print("DawDreamer initialization returned False — VST backend disabled.")
        except Exception as e:
            print(f"DawDreamer failed to initialize ({e}) — VST backend disabled.")

    daw_thread = threading.Thread(
        target=_init_daw_worker,
        name="dawdreamer-init",
        daemon=True,
    )
    daw_thread.start()

    # Launch main window
    from gui.main_window import MainWindow
    window = MainWindow(audio_engine=audio, dawdreamer_engine=daw, base_dir=BASE_DIR)
    window.show()

    exit_code = app.exec()

    # Cleanup — wait briefly for the init thread if the user closed
    # the window before Kontakt finished loading. If it's still going
    # we let it die with the process (daemon=True).
    audio.shutdown()
    if daw_thread.is_alive():
        print("Waiting up to 5s for DawDreamer init thread to finish...")
        daw_thread.join(timeout=5.0)
    daw.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
