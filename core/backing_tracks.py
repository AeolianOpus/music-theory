"""
Backing track engine.
Generates drum and bass loops using MIDI patterns played through FluidSynth.
"""

from __future__ import annotations
import threading
import time
from typing import Optional, Callable
from .audio_engine import AudioEngine, DRUM_CHANNEL, BASS_CHANNEL


# ── GM Drum Map (channel 9) ──────────────────────────────────────────
DRUM_NOTES = {
    "kick":         36,
    "snare":        38,
    "side_stick":   37,
    "closed_hat":   42,
    "open_hat":     46,
    "pedal_hat":    44,
    "ride":         51,
    "ride_bell":    53,
    "crash":        49,
    "crash_2":      57,
    "tom_high":     50,
    "tom_mid":      47,
    "tom_low":      45,
    "tom_floor":    43,
    "clap":         39,
    "tambourine":   54,
    "cowbell":      56,
}

# ── Drum Patterns ─────────────────────────────────────────────────────
# Each pattern is a list of "steps" (16th notes in a 4/4 bar = 16 steps).
# Each step is a list of (drum_name, velocity) tuples.

DrumStep = list[tuple[str, int]]
DrumPattern = list[DrumStep]


def _build_pattern(hits: dict[str, list[tuple[int, int]]]) -> DrumPattern:
    """
    Build a 16-step pattern from a dict of {drum_name: [(step, velocity), ...]}.
    """
    pattern: DrumPattern = [[] for _ in range(16)]
    for drum, steps in hits.items():
        for step, vel in steps:
            pattern[step].append((drum, vel))
    return pattern


DRUM_PATTERNS: dict[str, DrumPattern] = {
    "Rock Basic": _build_pattern({
        "kick":       [(0, 110), (8, 110)],
        "snare":      [(4, 100), (12, 100)],
        "closed_hat": [(i, 80) for i in range(0, 16, 2)],
    }),
    "Rock Drive": _build_pattern({
        "kick":       [(0, 110), (6, 90), (8, 110), (14, 80)],
        "snare":      [(4, 105), (12, 105)],
        "closed_hat": [(i, 75) for i in range(16)],
        "open_hat":   [(7, 70), (15, 70)],
    }),
    "Blues Shuffle": _build_pattern({
        "kick":       [(0, 100), (9, 95)],
        "snare":      [(4, 95), (12, 95)],
        "closed_hat": [(0, 80), (2, 50), (4, 80), (6, 50),
                       (8, 80), (10, 50), (12, 80), (14, 50)],
    }),
    "Funk": _build_pattern({
        "kick":       [(0, 110), (3, 80), (7, 90), (10, 85)],
        "snare":      [(4, 100), (12, 100)],
        "closed_hat": [(i, 70) for i in range(16)],
        "open_hat":   [(6, 75), (14, 75)],
    }),
    "Jazz Ride": _build_pattern({
        "ride":       [(0, 90), (3, 60), (4, 85), (6, 55),
                       (8, 90), (11, 60), (12, 85), (14, 55)],
        "kick":       [(0, 70), (10, 60)],
        "closed_hat": [(4, 50), (12, 50)],
    }),
    "Ballad": _build_pattern({
        "kick":       [(0, 90), (12, 85)],
        "snare":      [(4, 75), (12, 80)],
        "closed_hat": [(i, 55) for i in range(0, 16, 2)],
        "ride":       [(0, 60), (8, 55)],
    }),
    "Metal": _build_pattern({
        "kick":       [(0, 120), (2, 110), (4, 120), (6, 110),
                       (8, 120), (10, 110), (12, 120), (14, 110)],
        "snare":      [(4, 115), (12, 115)],
        "closed_hat": [(i, 90) for i in range(16)],
        "crash":      [(0, 100)],
    }),
    "Latin": _build_pattern({
        "kick":       [(0, 95), (6, 85), (10, 90)],
        "snare":      [(4, 85), (12, 85)],
        "closed_hat": [(i, 70) for i in range(16)],
        "side_stick": [(2, 65), (8, 65), (14, 65)],
        "cowbell":    [(0, 60), (4, 55), (8, 60), (12, 55)],
    }),
    "Bossa Nova": _build_pattern({
        "kick":       [(0, 80), (6, 75), (10, 75)],
        "side_stick": [(3, 70), (7, 70), (11, 70), (15, 70)],
        "closed_hat": [(i, 55) for i in range(0, 16, 2)],
    }),
    "Half-Time": _build_pattern({
        "kick":       [(0, 105)],
        "snare":      [(8, 100)],
        "closed_hat": [(i, 70) for i in range(0, 16, 4)],
        "open_hat":   [(12, 65)],
    }),
    "Metronome": _build_pattern({
        "side_stick": [(0, 110), (4, 80), (8, 80), (12, 80)],
    }),
}

# ── Bass Patterns ─────────────────────────────────────────────────────
# Each bass pattern is a list of (step, interval_from_root, velocity, duration_steps).
# interval_from_root: 0 = root, 7 = fifth, 12 = octave, etc.
BassHit = tuple[int, int, int, int]   # (step, interval, velocity, duration)
BassPattern = list[BassHit]

BASS_PATTERNS: dict[str, BassPattern] = {
    "Root Quarter": [
        (0, 0, 100, 4), (4, 0, 90, 4), (8, 0, 100, 4), (12, 0, 90, 4),
    ],
    "Root-Fifth": [
        (0, 0, 100, 4), (4, 7, 90, 4), (8, 0, 95, 4), (12, 7, 85, 4),
    ],
    "Walking Bass": [
        (0, 0, 100, 3), (4, 4, 85, 3), (8, 7, 90, 3), (12, 5, 80, 3),
    ],
    "Root Eighth": [
        (0, 0, 100, 2), (2, 0, 75, 2), (4, 0, 95, 2), (6, 0, 70, 2),
        (8, 0, 100, 2), (10, 0, 75, 2), (12, 0, 95, 2), (14, 0, 70, 2),
    ],
    "Funk Bass": [
        (0, 0, 110, 2), (3, 0, 70, 1), (4, 0, 60, 2), (7, 7, 90, 1),
        (8, 0, 100, 2), (10, 0, 65, 1), (12, 5, 85, 2), (14, 0, 75, 1),
    ],
    "Reggae": [
        (0, 0, 50, 2), (4, 0, 95, 4), (12, 7, 85, 4),
    ],
    "Driving Eighth": [
        (i, 0 if i % 4 == 0 else 0, 100 if i % 4 == 0 else 75, 2)
        for i in range(0, 16, 2)
    ],
}


class BackingTrackEngine:
    """
    Plays drum and bass loops in sync at a given tempo.
    Runs in a background thread.
    """

    def __init__(self, audio_engine: AudioEngine):
        self._audio = audio_engine
        self._playing = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Current settings
        self.tempo: float = 120.0                # BPM
        self.drum_pattern_name: str = "Rock Basic"
        self.bass_pattern_name: str = "Root Quarter"
        self.bass_root_midi: int = 40            # E2 default
        self.drum_volume: int = 100
        self.bass_volume: int = 100
        self.drums_enabled: bool = True
        self.bass_enabled: bool = True

    @property
    def is_playing(self) -> bool:
        return self._playing

    def start(self) -> None:
        """Start the backing track loop."""
        if self._playing:
            return
        self._playing = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the backing track."""
        self._playing = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._audio.all_notes_off(DRUM_CHANNEL)
        self._audio.all_notes_off(BASS_CHANNEL)

    def _loop(self) -> None:
        """Main playback loop — runs in background thread."""
        drum_pattern = DRUM_PATTERNS.get(self.drum_pattern_name, DRUM_PATTERNS["Rock Basic"])
        bass_pattern = BASS_PATTERNS.get(self.bass_pattern_name, BASS_PATTERNS["Root Quarter"])

        while self._playing:
            # Time per 16th note step
            step_duration = 60.0 / self.tempo / 4.0

            for step in range(16):
                if not self._playing:
                    break

                step_start = time.time()

                # ── Drums ──
                if self.drums_enabled and step < len(drum_pattern):
                    for drum_name, velocity in drum_pattern[step]:
                        midi_note = DRUM_NOTES.get(drum_name)
                        if midi_note is not None:
                            vel = int(velocity * self.drum_volume / 127)
                            self._audio.note_on(DRUM_CHANNEL, midi_note, vel)

                # ── Bass ──
                if self.bass_enabled:
                    for bstep, interval, velocity, dur in bass_pattern:
                        if bstep == step:
                            midi = self.bass_root_midi + interval
                            vel = int(velocity * self.bass_volume / 127)
                            self._audio.note_on(BASS_CHANNEL, midi, vel)
                            # Schedule note-off after duration
                            off_time = dur * step_duration
                            threading.Timer(
                                off_time,
                                self._audio.note_off,
                                args=(BASS_CHANNEL, midi)
                            ).start()

                # Sleep remainder of step
                elapsed = time.time() - step_start
                remaining = step_duration - elapsed
                if remaining > 0:
                    time.sleep(remaining)

    def set_tempo(self, bpm: float) -> None:
        """Change tempo (takes effect next bar)."""
        self.tempo = max(30.0, min(300.0, bpm))

    def set_drum_pattern(self, name: str) -> None:
        if name in DRUM_PATTERNS:
            self.drum_pattern_name = name

    def set_bass_pattern(self, name: str) -> None:
        if name in BASS_PATTERNS:
            self.bass_pattern_name = name

    def set_bass_root(self, midi_note: int) -> None:
        """Set bass root note (should match current chord root)."""
        self.bass_root_midi = midi_note

    @staticmethod
    def get_drum_pattern_names() -> list[str]:
        return list(DRUM_PATTERNS.keys())

    @staticmethod
    def get_bass_pattern_names() -> list[str]:
        return list(BASS_PATTERNS.keys())
