"""
Bootstrap script for project initialization.
Handles venv patching, environment checks, etc.
Run this before importing project modules.
"""
import os
import sys
from pathlib import Path


def patch_fluidsynth_venv():
    """Auto-patch pyfluidsynth in venv to find FluidSynth DLL on Windows."""
    if sys.platform != "win32":
        return

    venv_fluidsynth = Path("venv/Lib/site-packages/fluidsynth.py")

    if not venv_fluidsynth.exists():
        return

    try:
        content = venv_fluidsynth.read_text()

        if "# Auto-patched for Scoop FluidSynth" in content:
            return  # Already patched

        home = Path.home()
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'from ctypes.util import find_library' in line:
                patch = f"""
# Auto-patched for FluidSynth support (Scoop + manual installs)
if hasattr(os, 'add_dll_directory'):
    search_paths = [
        r'C:\\ProgramData\\scoop\\apps\\fluidsynth\\current\\bin',
        r'{home}\\scoop\\apps\\fluidsynth\\current\\bin',
        r'C:\\tools\\fluidsynth\\bin',
        r'C:\\Program Files\\FluidSynth\\bin',
    ]
    for path in search_paths:
        if os.path.exists(path):
            os.add_dll_directory(path)
"""
                lines.insert(i + 1, patch)
                venv_fluidsynth.write_text('\n'.join(lines))
                print("✅ Auto-patched pyfluidsynth for FluidSynth")
                break
    except Exception as e:
        print(f"⚠️ Could not auto-patch pyfluidsynth: {e}")


def check_dependencies():
    """Check if required dependencies are available."""
    # Add future dependency checks here
    pass


def run_bootstrap():
    """Run all bootstrap tasks."""
    patch_fluidsynth_venv()
    check_dependencies()
    # Add more startup tasks here as needed


if __name__ == "__main__":
    run_bootstrap()