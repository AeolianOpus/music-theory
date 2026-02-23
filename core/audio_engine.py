"""
Audio engine using FluidSynth for real-time instrument playback.
Handles SoundFont loading, note/chord triggering, and instrument selection.
"""
from __future__ import annotations
import os
import sys
if sys.platform == "win32":
    # Try to find FluidSynth in common Scoop locations
    fluidsynth_paths = [
        r"C:\ProgramData\scoop\apps\fluidsynth\2.5.2\bin",  # PC (global install)
        r"C:\Users\Constantine\scoop\apps\fluidsynth\2.5.2\bin",  # Laptop (user install)
    ]
    
    fluidsynth_found = False
    for path in fluidsynth_paths:
        if os.path.exists(path):
            os.add_dll_directory(path)
            fluidsynth_found = True
            break
    
    if not fluidsynth_found:
        print("Warning: FluidSynth path not found in expected locations")
import time
import threading
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    import fluidsynth

try:
    import fluidsynth
    HAS_FLUIDSYNTH = True
except ImportError:
    HAS_FLUIDSYNTH = False


# General MIDI program numbers for common instruments
GM_PROGRAMS: dict[str, int] = {
    "acoustic_grand_piano": 0,
    "bright_piano": 1,
    "electric_grand": 2,
    "honky_tonk": 3,
    "electric_piano_1": 4,
    "electric_piano_2": 5,
    "harpsichord": 6,
    "clavinet": 7,
    "nylon_guitar": 24,
    "steel_guitar": 25,
    "jazz_guitar": 26,
    "clean_electric": 27,
    "muted_electric": 28,
    "overdriven_guitar": 29,
    "distortion_guitar": 30,
    "guitar_harmonics": 31,
    "acoustic_bass": 32,
    "finger_bass": 33,
    "pick_bass": 34,
    "fretless_bass": 35,
    "slap_bass_1": 36,
    "synth_bass_1": 38,
    "violin": 40,
    "cello": 42,
    "strings_ensemble": 48,
    "synth_strings": 50,
    "choir_aahs": 52,
    "trumpet": 56,
    "trombone": 57,
    "organ": 16,
    "church_organ": 19,
}

# Drum channel in GM is channel 9 (0-indexed)
DRUM_CHANNEL = 9

# Default channels
PIANO_CHANNEL = 0
GUITAR_CHANNEL = 1
BASS_CHANNEL = 2


class AudioEngine:
    """
    FluidSynth-based audio engine for real-time instrument playback.
    """

    def __init__(self, soundfont_path: Optional[str] = None) -> None:
        self._synth: Any = None
        self._sfid: Optional[int] = None
        self._soundfont_path: Optional[str] = soundfont_path
        self._initialized: bool = False
        self._lock: threading.Lock = threading.Lock()

    def initialize(self, soundfont_path: Optional[str] = None) -> bool:
        """
        Initialize FluidSynth and load a SoundFont.
        Returns True on success, False if FluidSynth is not available.
        """
        if not HAS_FLUIDSYNTH:
            print("Warning: pyfluidsynth not installed. Audio disabled.")
            return False

        sf_path: Optional[str] = soundfont_path or self._soundfont_path
        if not sf_path or not os.path.exists(sf_path):
            print(f"Warning: SoundFont not found at '{sf_path}'. Audio disabled.")
            return False

        import fluidsynth

        try:
            with self._lock:
                self._synth = fluidsynth.Synth(gain=0.8, samplerate=44100)
                self._synth.start()  # Use default audio driver
                self._sfid = self._synth.sfload(sf_path)
                if self._sfid == -1:
                    print("Failed to load SoundFont.")
                    return False

                # Set up default instruments
                self._synth.program_select(PIANO_CHANNEL, self._sfid, 0,
                                           GM_PROGRAMS["acoustic_grand_piano"])
                self._synth.program_select(GUITAR_CHANNEL, self._sfid, 0,
                                           GM_PROGRAMS["clean_electric"])
                self._synth.program_select(BASS_CHANNEL, self._sfid, 0,
                                           GM_PROGRAMS["finger_bass"])
                # Drum channel
                self._synth.program_select(DRUM_CHANNEL, self._sfid, 128, 0)

                self._initialized = True
                return True
        except Exception as e:
            print(f"FluidSynth initialization error: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._synth is not None

    def set_instrument(self, channel: int, program: int) -> None:
        """Change the GM instrument on a channel."""
        if not self.is_ready:
            return
        with self._lock:
            self._synth.program_select(channel, self._sfid, 0, program)

    def set_instrument_by_name(self, channel: int, name: str) -> None:
        """Change instrument by name (see GM_PROGRAMS)."""
        if name in GM_PROGRAMS:
            self.set_instrument(channel, GM_PROGRAMS[name])

    def note_on(self, channel: int, midi_note: int, velocity: int = 100) -> None:
        """Trigger a note on."""
        if not self.is_ready:
            return
        with self._lock:
            self._synth.noteon(channel, midi_note, velocity)

    def note_off(self, channel: int, midi_note: int) -> None:
        """Release a note."""
        if not self.is_ready:
            return
        with self._lock:
            self._synth.noteoff(channel, midi_note)

    def play_note(self, channel: int, midi_note: int,
                  duration: float = 0.5, velocity: int = 100) -> None:
        """Play a note for a given duration (blocking)."""
        self.note_on(channel, midi_note, velocity)
        time.sleep(duration)
        self.note_off(channel, midi_note)

    def play_note_async(self, channel: int, midi_note: int,
                        duration: float = 0.5, velocity: int = 100) -> None:
        """Play a note in a background thread."""
        t = threading.Thread(target=self.play_note,
                             args=(channel, midi_note, duration, velocity),
                             daemon=True)
        t.start()

    def play_chord(self, channel: int, midi_notes: list[int],
                   duration: float = 1.0, velocity: int = 90) -> None:
        """Play multiple notes simultaneously (blocking)."""
        for note in midi_notes:
            self.note_on(channel, note, velocity)
        time.sleep(duration)
        for note in midi_notes:
            self.note_off(channel, note)

    def play_chord_async(self, channel: int, midi_notes: list[int],
                         duration: float = 1.0, velocity: int = 90) -> None:
        """Play a chord in a background thread."""
        t = threading.Thread(target=self.play_chord,
                             args=(channel, midi_notes, duration, velocity),
                             daemon=True)
        t.start()

    def play_arpeggio(self, channel: int, midi_notes: list[int],
                      note_duration: float = 0.15, velocity: int = 90) -> None:
        """Play notes one at a time (arpeggiated), blocking."""
        for note in midi_notes:
            self.note_on(channel, note, velocity)
            time.sleep(note_duration)
        time.sleep(0.3)
        for note in midi_notes:
            self.note_off(channel, note)

    def play_arpeggio_async(self, channel: int, midi_notes: list[int],
                            note_duration: float = 0.15, velocity: int = 90) -> None:
        """Arpeggiate in a background thread."""
        t = threading.Thread(target=self.play_arpeggio,
                             args=(channel, midi_notes, note_duration, velocity),
                             daemon=True)
        t.start()

    def all_notes_off(self, channel: Optional[int] = None) -> None:
        """Silence all notes on a channel (or all channels)."""
        if not self.is_ready:
            return
        with self._lock:
            if channel is not None:
                self._synth.cc(channel, 123, 0)
            else:
                for ch in range(16):
                    self._synth.cc(ch, 123, 0)

    def set_volume(self, channel: int, volume: int) -> None:
        """Set channel volume (0-127)."""
        if not self.is_ready:
            return
        with self._lock:
            self._synth.cc(channel, 7, max(0, min(127, volume)))

    def set_reverb(self, roomsize: float = 0.6, damp: float = 0.4,
                   width: float = 0.8, level: float = 0.7) -> None:
        """Configure reverb effect."""
        if not self.is_ready:
            return
        with self._lock:
            self._synth.set_reverb(roomsize, damp, width, level)

    def shutdown(self) -> None:
        """Clean up FluidSynth resources."""
        if self._synth is not None:
            with self._lock:
                try:
                    self._synth.delete()
                except Exception:
                    pass
                self._synth = None
                self._initialized = False