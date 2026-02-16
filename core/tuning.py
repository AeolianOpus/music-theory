"""
Tuning system for guitar (and other stringed instruments).
Supports standard tunings, drop tunings, and arbitrary half-step shifts.
Each string is represented as a MIDI note number.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .music_theory import note_name, parse_note, SHARP_NAMES


# MIDI note for each note name at octave 0
# C0=12, C1=24, ..., C4=60 (middle C), A4=69 (440Hz)
def note_to_midi(note_str: str, octave: int) -> int:
    """Convert note name + octave to MIDI note number."""
    pc = parse_note(note_str)
    return 12 * (octave + 1) + pc


def midi_to_note(midi: int) -> tuple[str, int]:
    """Convert MIDI note number to (note_name, octave)."""
    octave = (midi // 12) - 1
    pc = midi % 12
    return note_name(pc), octave


def midi_to_display(midi: int) -> str:
    """MIDI note number to display string like 'E2', 'A4'."""
    name, octave = midi_to_note(midi)
    return f"{name}{octave}"


# ── Guitar Tunings ────────────────────────────────────────────────────
# Defined as MIDI note numbers, low string to high string (6 strings).

GUITAR_TUNINGS: dict[str, tuple[int, ...]] = {
    "Standard (EADGBE)":        (40, 45, 50, 55, 59, 64),  # E2 A2 D3 G3 B3 E4
    "Drop D":                   (38, 45, 50, 55, 59, 64),  # D2 A2 D3 G3 B3 E4
    "Drop C":                   (36, 43, 48, 53, 57, 62),  # C2 G2 C3 F3 A3 D4
    "Drop B":                   (35, 42, 47, 52, 56, 61),  # B1 F#2 B2 E3 G#3 C#4
    "Open G":                   (38, 43, 50, 55, 59, 62),  # D2 G2 D3 G3 B3 D4
    "Open D":                   (38, 45, 50, 54, 57, 62),  # D2 A2 D3 F#3 A3 D4
    "Open E":                   (40, 47, 52, 56, 59, 64),  # E2 B2 E3 G#3 B3 E4
    "Open A":                   (40, 45, 52, 57, 61, 64),  # E2 A2 E3 A3 C#4 E4
    "DADGAD":                   (38, 45, 50, 55, 57, 62),  # D2 A2 D3 G3 A3 D4
    "Open C":                   (36, 43, 48, 55, 60, 64),  # C2 G2 C3 G3 C4 E4
    "Half Step Down (Eb)":      (39, 44, 49, 54, 58, 63),  # Eb2 Ab2 Db3 Gb3 Bb3 Eb4
    "Full Step Down (D)":       (38, 43, 48, 53, 57, 62),  # D2 G2 C3 F3 A3 D4
    "NST (New Standard)":       (36, 43, 50, 57, 62, 67),  # C2 G2 D3 A3 D4 G4
}

# 7-string extensions
GUITAR_TUNINGS_7: dict[str, tuple[int, ...]] = {
    "Standard 7 (BEADGBE)":     (35, 40, 45, 50, 55, 59, 64),
    "Drop A 7":                 (33, 40, 45, 50, 55, 59, 64),
}

# Bass tunings (4, 5 string)
BASS_TUNINGS: dict[str, tuple[int, ...]] = {
    "Standard Bass (EADG)":     (28, 33, 38, 43),  # E1 A1 D2 G2
    "5-String Bass (BEADG)":    (23, 28, 33, 38, 43),
    "Drop D Bass":              (26, 33, 38, 43),
    "Half Step Down Bass":      (27, 32, 37, 42),
}


@dataclass
class Tuning:
    """Represents an instrument tuning configuration."""
    name: str
    string_midi: tuple[int, ...]   # MIDI note per string, low→high
    instrument: str = "guitar"     # "guitar", "bass", "custom"
    num_frets: int = 24

    @classmethod
    def from_preset(cls, preset_name: str) -> "Tuning":
        """Load a preset tuning by name."""
        if preset_name in GUITAR_TUNINGS:
            return cls(name=preset_name, string_midi=GUITAR_TUNINGS[preset_name],
                       instrument="guitar")
        if preset_name in GUITAR_TUNINGS_7:
            return cls(name=preset_name, string_midi=GUITAR_TUNINGS_7[preset_name],
                       instrument="guitar")
        if preset_name in BASS_TUNINGS:
            return cls(name=preset_name, string_midi=BASS_TUNINGS[preset_name],
                       instrument="bass")
        raise ValueError(f"Unknown tuning preset: '{preset_name}'")

    @classmethod
    def custom(cls, string_notes: list[str], name: str = "Custom") -> "Tuning":
        """
        Create custom tuning from note strings like ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'].
        """
        midi_notes = []
        for ns in string_notes:
            # Parse "E2" → note E, octave 2
            note_part = ns.rstrip("0123456789")
            octave_part = ns[len(note_part):]
            if not octave_part:
                raise ValueError(f"Missing octave in '{ns}' (e.g. 'E2')")
            midi_notes.append(note_to_midi(note_part, int(octave_part)))
        return cls(name=name, string_midi=tuple(midi_notes), instrument="custom")

    def shift(self, semitones: int) -> "Tuning":
        """Return a new Tuning shifted by N semitones (positive=up, negative=down)."""
        shifted = tuple(m + semitones for m in self.string_midi)
        direction = "up" if semitones > 0 else "down"
        new_name = f"{self.name} ({abs(semitones)} half-step{'s' if abs(semitones)!=1 else ''} {direction})"
        return Tuning(name=new_name, string_midi=shifted,
                      instrument=self.instrument, num_frets=self.num_frets)

    @property
    def num_strings(self) -> int:
        return len(self.string_midi)

    def string_names(self) -> list[str]:
        """Display names for each open string."""
        return [midi_to_display(m) for m in self.string_midi]

    def note_at(self, string_idx: int, fret: int) -> int:
        """MIDI note number at a given string and fret."""
        return self.string_midi[string_idx] + fret

    def note_name_at(self, string_idx: int, fret: int) -> str:
        """Note name at a given string and fret."""
        midi = self.note_at(string_idx, fret)
        return note_name(midi % 12)

    def fret_for_note(self, string_idx: int, target_pc: int) -> list[int]:
        """
        Find all frets on a string that produce a given pitch class.
        Returns fret numbers within the fretboard range.
        """
        open_midi = self.string_midi[string_idx]
        open_pc = open_midi % 12
        offset = (target_pc - open_pc) % 12
        frets = []
        fret = offset
        while fret <= self.num_frets:
            frets.append(fret)
            fret += 12
        return frets

    def to_dict(self) -> dict:
        """Serialize for saving."""
        return {
            "name": self.name,
            "string_midi": list(self.string_midi),
            "instrument": self.instrument,
            "num_frets": self.num_frets,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Tuning":
        return cls(
            name=d["name"],
            string_midi=tuple(d["string_midi"]),
            instrument=d.get("instrument", "guitar"),
            num_frets=d.get("num_frets", 24),
        )


def get_all_tuning_presets() -> dict[str, dict[str, tuple[int, ...]]]:
    """Return all preset tunings grouped by type."""
    return {
        "Guitar (6-string)": GUITAR_TUNINGS,
        "Guitar (7-string)": GUITAR_TUNINGS_7,
        "Bass": BASS_TUNINGS,
    }
