"""
Playback engine for chord progressions.

Schedules a ChordProgression as a real-time backing track using FluidSynth.
Supports multi-instrument layering (chord + bass + pad + choir + drone),
style presets, click track, looping, and live tempo changes.

Architecture: one master playback thread per session. The thread loops
through the progression, scheduling MIDI events on the AudioEngine.
The caller's thread returns immediately after play_progression().
"""

from __future__ import annotations
import threading
import time
from typing import Optional

from .music_theory import ChordProgression, Chord
from .audio_engine import (
    AudioEngine,
    GM_PROGRAMS,
    GM_DRUMS,
    DRUM_CHANNEL,
)


# ── Channel allocation ────────────────────────────────────────────
# AudioEngine reserves 0-2 and 9. We use 3-5 for pad/choir/drone.
CHORD_CHANNEL = 0       # default — overridable per call
BASS_CHANNEL = 2        # bass note layer
PAD_CHANNEL = 3         # warm sustain pad
CHOIR_CHANNEL = 4       # dark choir layer (Yngwie territory)
DRONE_CHANNEL = 5       # Taurus-style synth bass drone

# ── Soundfont routing ─────────────────────────────────────────────
# DEFAULT_SOUNDFONT is the workhorse SF2 — used for any instrument
# that doesn't have an explicit override in INSTRUMENT_SOURCES.
# INSTRUMENT_SOURCES maps a GM-instrument-name (as used in STYLE_PRESETS
# and GM_PROGRAMS) to the name of the soundfont that should play it.
# Names here must match the names passed to audio.load_soundfont(name, ...)
# in the bootstrap code (e.g. test_playback.py, app.py).
#
# Empty for now: every instrument resolves to DEFAULT_SOUNDFONT until
# we hear what's actually weak and fill in targeted overrides.
DEFAULT_SOUNDFONT = "compifont"
INSTRUMENT_SOURCES: dict[str, str] = {}

# ── Style presets ─────────────────────────────────────────────────
# Each preset assigns GM instrument names to the five layers.
# A None value means that layer is silent for this style.

STYLE_PRESETS: dict[str, dict[str, Optional[str]]] = {
    "generic": {
        "chord_instrument": "acoustic_grand_piano",
        "bass_instrument": "finger_bass",
        "pad_instrument": "strings_ensemble",
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "rock": {
        "chord_instrument": "clean_electric",
        "bass_instrument": "pick_bass",
        "pad_instrument": None,
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "metal": {
        "chord_instrument": "distortion_guitar",
        "bass_instrument": "pick_bass",
        "pad_instrument": "synth_strings",
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "neoclassical": {
        "chord_instrument": "harpsichord",
        "bass_instrument": "cello",
        "pad_instrument": "strings_ensemble",
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "neoclassical_metal": {
        "chord_instrument": "distortion_guitar",
        "bass_instrument": "cello",
        "pad_instrument": "strings_ensemble",
        "choir_instrument": "choir_aahs",
        "drone_instrument": "synth_bass_2",
    },
    "jens_organ": {
        "chord_instrument": "harpsichord",
        "bass_instrument": "cello",
        "pad_instrument": "church_organ",
        "choir_instrument": "choir_aahs",
        "drone_instrument": "synth_bass_2",
    },
    "bach_toccata": {
        "chord_instrument": "church_organ",
        "bass_instrument": "church_organ",
        "pad_instrument": None,
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "jazz": {
        "chord_instrument": "electric_piano_1",
        "bass_instrument": "fretless_bass",
        "pad_instrument": None,
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "fusion": {
        "chord_instrument": "electric_piano_1",
        "bass_instrument": "fretless_bass",
        "pad_instrument": "synth_strings",
        "choir_instrument": None,
        "drone_instrument": None,
    },
    "blues": {
        "chord_instrument": "electric_piano_1",
        "bass_instrument": "acoustic_bass",
        "pad_instrument": None,
        "choir_instrument": None,
        "drone_instrument": None,
    },
}


# ── Voicing helpers ───────────────────────────────────────────────
# MIDI octave convention: C4 = MIDI 60 (middle C).
# So octave N's C is at MIDI (N + 1) * 12. E.g. C2 = 36, C3 = 48, C4 = 60.

def _midi_for(pitch_class: int, octave: int) -> int:
    """Convert a pitch class (0-11) at a given octave to MIDI note number."""
    return (octave + 1) * 12 + (pitch_class % 12)


def _bass_note(root_pc: int) -> int:
    """Bass note in octave 2 (around MIDI 36-47)."""
    return _midi_for(root_pc, 2)


def _drone_notes(root_pc: int) -> list[int]:
    """Taurus pedal: root + fifth in octave 1 (around MIDI 24-35)."""
    root = _midi_for(root_pc, 1)
    fifth = _midi_for(root_pc + 7, 1)
    return [root, fifth]


def _chord_voicing(chord: Chord, base_octave: int = 3) -> list[int]:
    """
    Block voicing of a chord starting at base_octave (default octave 3).
    For Am at octave 3: A3-C4-E4 (MIDI 57, 60, 64).

    Stacks chord tones in ascending order, bumping octaves to keep the line going up.
    """
    notes = [_midi_for(chord.root, base_octave)]
    for pc in chord.pitch_classes:
        if pc == chord.root:
            continue
        candidate = _midi_for(pc, base_octave)
        while candidate <= notes[-1]:
            candidate += 12
        notes.append(candidate)
    return notes


def _pad_voicing(chord: Chord) -> list[int]:
    """Pad voicing in octave 4 — sits above the chord voicing."""
    return _chord_voicing(chord, base_octave=4)


def _choir_voicing(chord: Chord) -> list[int]:
    """Choir voicing in octave 3, sits with the chord voicing for warmth."""
    return _chord_voicing(chord, base_octave=3)

# ── Velocity defaults per layer ───────────────────────────────────
# Lower values for pad/choir/drone so they sit underneath the chord stab,
# not in front of it. Drum click also lower to be a reference, not a beat.
VELOCITY_CHORD = 95
VELOCITY_BASS = 90
VELOCITY_PAD = 55
VELOCITY_CHOIR = 45
VELOCITY_DRONE = 70
VELOCITY_CLICK = 60
VELOCITY_CLICK_ACCENT = 90  # beat 1 of each bar


class PlaybackEngine:
    """
    Real-time backing track engine. Schedules a ChordProgression as audio
    on a multi-channel AudioEngine. One master playback thread per session.

    Usage:
        audio = AudioEngine(soundfont_path="path/to.sf2")
        audio.initialize()
        playback = PlaybackEngine(audio)
        playback.play_progression(prog, tempo=100, style="neoclassical_metal", loop=True)
        # ... jam ...
        playback.stop()
    """

    def __init__(self, audio_engine: AudioEngine) -> None:
        self.audio: AudioEngine = audio_engine
        self._thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        self._tempo_lock: threading.Lock = threading.Lock()
        self._current_tempo: int = 120
        self._current_volume: int = 100  # 0-127

    # ── Public API ──────────────────────────────────────────

    def play_progression(
        self,
        progression: ChordProgression,
        tempo: int = 120,
        style: str = "generic",
        chord_instrument: Optional[str] = None,
        bass_instrument: Optional[str] = None,
        pad_instrument: Optional[str] = None,
        choir_instrument: Optional[str] = None,
        drone_instrument: Optional[str] = None,
        click_track: bool = True,
        loop: bool = False,
        bars_per_chord: float = 1.0,
    ) -> None:
        """
        Start playing the given progression. Returns immediately;
        playback runs in a background thread.

        Args:
            progression: ChordProgression to play.
            tempo: BPM (default 120). Can be changed live via set_tempo().
            style: preset name from STYLE_PRESETS (default "generic").
            chord_instrument, bass_instrument, ...: explicit overrides.
                Each defaults to the preset's value if not provided.
                Pass empty string "" to silence a layer that the preset enables.
            click_track: play a hi-hat tick on every beat (default True).
            loop: repeat the progression until stop() is called (default False).
            bars_per_chord: how many bars each chord lasts (default 1.0).
        """
        if not self.audio.is_ready:
            print("PlaybackEngine: AudioEngine not initialized. Call audio.initialize() first.")
            return

        if not progression.chords:
            return

        # Stop any current playback before starting new
        self.stop()

        # Resolve preset + overrides into final instrument selection.
        # Explicit non-None args win; "" means silence; None means "use preset".
        preset = STYLE_PRESETS.get(style, STYLE_PRESETS["generic"])

        def _resolve(arg: Optional[str], preset_key: str) -> Optional[str]:
            if arg is None:
                return preset.get(preset_key)
            if arg == "":
                return None
            return arg

        instruments = {
            "chord":  _resolve(chord_instrument,  "chord_instrument"),
            "bass":   _resolve(bass_instrument,   "bass_instrument"),
            "pad":    _resolve(pad_instrument,    "pad_instrument"),
            "choir":  _resolve(choir_instrument,  "choir_instrument"),
            "drone":  _resolve(drone_instrument,  "drone_instrument"),
        }

        # Apply instruments to channels, routing each to its source soundfont.
        # INSTRUMENT_SOURCES lookup falls back to DEFAULT_SOUNDFONT.
        def _sf_for(instrument_name: str) -> str:
            return INSTRUMENT_SOURCES.get(instrument_name, DEFAULT_SOUNDFONT)

        if instruments["chord"]:
            self.audio.set_instrument_by_name(CHORD_CHANNEL, instruments["chord"],
                                              _sf_for(instruments["chord"]))
        if instruments["bass"]:
            self.audio.set_instrument_by_name(BASS_CHANNEL, instruments["bass"],
                                              _sf_for(instruments["bass"]))
        if instruments["pad"]:
            self.audio.set_instrument_by_name(PAD_CHANNEL, instruments["pad"],
                                              _sf_for(instruments["pad"]))
        if instruments["choir"]:
            self.audio.set_instrument_by_name(CHOIR_CHANNEL, instruments["choir"],
                                              _sf_for(instruments["choir"]))
        if instruments["drone"]:
            self.audio.set_instrument_by_name(DRONE_CHANNEL, instruments["drone"],
                                              _sf_for(instruments["drone"]))

        # Set per-layer volume (lower for pad/choir to sit underneath)
        self.audio.set_volume(CHORD_CHANNEL, 110)
        self.audio.set_volume(BASS_CHANNEL, 100)
        self.audio.set_volume(PAD_CHANNEL, 70)
        self.audio.set_volume(CHOIR_CHANNEL, 60)
        self.audio.set_volume(DRONE_CHANNEL, 80)

        with self._tempo_lock:
            self._current_tempo = tempo

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._playback_loop,
            args=(progression, instruments, click_track, loop, bars_per_chord),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop playback. Blocks briefly until the thread cleans up."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        # Silence everything in case stop() interrupted mid-chord
        self.audio.all_notes_off()

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_tempo(self, bpm: int) -> None:
        """Change tempo on the fly. Takes effect at the next chord change."""
        with self._tempo_lock:
            self._current_tempo = max(20, min(300, bpm))

    def set_volume(self, level: int) -> None:
        """Master volume 0-127 (applied as channel volume across all layers)."""
        self._current_volume = max(0, min(127, level))
        # Scale all layer volumes proportionally to the master.
        scale = self._current_volume / 100.0
        self.audio.set_volume(CHORD_CHANNEL, int(110 * scale))
        self.audio.set_volume(BASS_CHANNEL,  int(100 * scale))
        self.audio.set_volume(PAD_CHANNEL,   int(70  * scale))
        self.audio.set_volume(CHOIR_CHANNEL, int(60  * scale))
        self.audio.set_volume(DRONE_CHANNEL, int(80  * scale))

    # ── Internal playback loop ──────────────────────────────

    def _playback_loop(
        self,
        progression: ChordProgression,
        instruments: dict[str, Optional[str]],
        click_track: bool,
        loop: bool,
        bars_per_chord: float,
    ) -> None:
        """The master playback thread. Runs until stop_event or progression ends."""
        try:
            while not self._stop_event.is_set():
                for chord in progression.chords:
                    if self._stop_event.is_set():
                        break
                    self._play_one_chord(chord, instruments, click_track, bars_per_chord)
                if not loop:
                    break
        finally:
            # Always silence everything on exit
            self.audio.all_notes_off()

    def _play_one_chord(
        self,
        chord: Chord,
        instruments: dict[str, Optional[str]],
        click_track: bool,
        bars_per_chord: float,
    ) -> None:
        """Play one chord for its bar duration with all enabled layers."""
        # Get current tempo (may have changed mid-playback)
        with self._tempo_lock:
            bpm = self._current_tempo

        beats_per_bar = 4
        seconds_per_beat = 60.0 / bpm
        total_beats = int(beats_per_bar * bars_per_chord)
        bar_duration = total_beats * seconds_per_beat

        # Determine notes per layer
        bass_note = _bass_note(chord.root) if instruments["bass"] else None
        chord_notes = _chord_voicing(chord) if instruments["chord"] else None
        pad_notes = _pad_voicing(chord) if instruments["pad"] else None
        choir_notes = _choir_voicing(chord) if instruments["choir"] else None
        drone_notes = _drone_notes(chord.root) if instruments["drone"] else None

        # Note-on for all layers
        if bass_note is not None:
            self.audio.note_on(BASS_CHANNEL, bass_note, VELOCITY_BASS)
        if chord_notes:
            for n in chord_notes:
                self.audio.note_on(CHORD_CHANNEL, n, VELOCITY_CHORD)
        if pad_notes:
            for n in pad_notes:
                self.audio.note_on(PAD_CHANNEL, n, VELOCITY_PAD)
        if choir_notes:
            for n in choir_notes:
                self.audio.note_on(CHOIR_CHANNEL, n, VELOCITY_CHOIR)
        if drone_notes:
            for n in drone_notes:
                self.audio.note_on(DRONE_CHANNEL, n, VELOCITY_DRONE)

        # Schedule click-track ticks across the bar duration
        # We sleep one beat at a time so the stop_event is checked frequently.
        for beat_idx in range(total_beats):
            if self._stop_event.is_set():
                break
            if click_track:
                vel = VELOCITY_CLICK_ACCENT if beat_idx == 0 else VELOCITY_CLICK
                self.audio.note_on(DRUM_CHANNEL, GM_DRUMS["closed_hat"], vel)
            time.sleep(seconds_per_beat)
            if click_track:
                self.audio.note_off(DRUM_CHANNEL, GM_DRUMS["closed_hat"])

        # Note-off for all layers (small gap before next chord)
        if bass_note is not None:
            self.audio.note_off(BASS_CHANNEL, bass_note)
        if chord_notes:
            for n in chord_notes:
                self.audio.note_off(CHORD_CHANNEL, n)
        if pad_notes:
            for n in pad_notes:
                self.audio.note_off(PAD_CHANNEL, n)
        if choir_notes:
            for n in choir_notes:
                self.audio.note_off(CHOIR_CHANNEL, n)
        if drone_notes:
            for n in drone_notes:
                self.audio.note_off(DRONE_CHANNEL, n)