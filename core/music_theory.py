"""
Core music theory primitives: notes, intervals, and chord construction.
All pitch classes use integer notation (0=C, 1=C#, ... 11=B).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# ── Note names ────────────────────────────────────────────────────────
# Sharps are the canonical representation; flats are aliases for display.
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
GUITAR_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Lookup: name → pitch class (handles both sharp and flat input)
NAME_TO_PC: dict[str, int] = {}
for i, name in enumerate(SHARP_NAMES):
    NAME_TO_PC[name] = i
    NAME_TO_PC[name.lower()] = i
for i, name in enumerate(FLAT_NAMES):
    NAME_TO_PC[name] = i
    NAME_TO_PC[name.lower()] = i
# Common enharmonic aliases
NAME_TO_PC.update({"Cb": 11, "cb": 11, "B#": 0, "b#": 0,
                    "E#": 5, "e#": 5, "Fb": 4, "fb": 4})

USE_GUITAR_NAMES = True

def note_name(pc: int, prefer_flat: bool = False) -> str:
    """Return the display name for a pitch class (0-11)."""
    pc = pc % 12
    if USE_GUITAR_NAMES:
        return GUITAR_NAMES[pc]
    return FLAT_NAMES[pc] if prefer_flat else SHARP_NAMES[pc]

def parse_note(name: str) -> int:
    """Parse a note name string to pitch class. Raises ValueError if invalid."""
    name = name.strip()
    if name in NAME_TO_PC:
        return NAME_TO_PC[name]
    raise ValueError(f"Unknown note: '{name}'")

# ── Intervals ─────────────────────────────────────────────────────────
INTERVAL_NAMES = {
    0: "Unison", 1: "Minor 2nd", 2: "Major 2nd", 3: "Minor 3rd",
    4: "Major 3rd", 5: "Perfect 4th", 6: "Tritone", 7: "Perfect 5th",
    8: "Minor 6th", 9: "Major 6th", 10: "Minor 7th", 11: "Major 7th",
}

INTERVAL_SHORT = {
    0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
    6: "b5", 7: "5", 8: "#5", 9: "6", 10: "b7", 11: "7",
}


# ── Chord definitions ────────────────────────────────────────────────
# Intervals from root for each chord quality.
CHORD_FORMULAS: dict[str, tuple[int, ...]] = {
    # Triads
    "maj":    (0, 4, 7),
    "min":    (0, 3, 7),
    "dim":    (0, 3, 6),
    "aug":    (0, 4, 8),
    "sus2":   (0, 2, 7),
    "sus4":   (0, 5, 7),
    # Sevenths
    "maj7":   (0, 4, 7, 11),
    "min7":   (0, 3, 7, 10),
    "7":      (0, 4, 7, 10),     # dominant 7
    "dim7":   (0, 3, 6, 9),
    "m7b5":   (0, 3, 6, 10),     # half-diminished
    "minmaj7":(0, 3, 7, 11),
    "aug7":   (0, 4, 8, 10),
    "augmaj7":(0, 4, 8, 11),
    # Extended
    "9":      (0, 4, 7, 10, 14),
    "maj9":   (0, 4, 7, 11, 14),
    "min9":   (0, 3, 7, 10, 14),
    "11":     (0, 4, 7, 10, 14, 17),
    "min11":  (0, 3, 7, 10, 14, 17),
    "13":     (0, 4, 7, 10, 14, 17, 21),
    "min13":  (0, 3, 7, 10, 14, 17, 21),
    # Altered
    "7b5":    (0, 4, 6, 10),
    "7#5":    (0, 4, 8, 10),
    "7b9":    (0, 4, 7, 10, 13),
    "7#9":    (0, 4, 7, 10, 15),
    "add9":   (0, 4, 7, 14),
    "madd9":  (0, 3, 7, 14),
    "6":      (0, 4, 7, 9),
    "min6":   (0, 3, 7, 9),
    # Power chord
    "5":      (0, 7),
}

# Display-friendly quality names
QUALITY_DISPLAY: dict[str, str] = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug",
    "sus2": "sus2", "sus4": "sus4",
    "maj7": "maj7", "min7": "m7", "7": "7", "dim7": "dim7",
    "m7b5": "m7b5", "minmaj7": "m(maj7)", "aug7": "aug7", "augmaj7": "aug(maj7)",
    "9": "9", "maj9": "maj9", "min9": "m9",
    "11": "11", "min11": "m11", "13": "13", "min13": "m13",
    "7b5": "7b5", "7#5": "7#5", "7b9": "7b9", "7#9": "7#9",
    "add9": "add9", "madd9": "m(add9)", "6": "6", "min6": "m6", "5": "5",
}

# Full display names for UI buttons/dropdowns
QUALITY_FULL_NAMES: dict[str, str] = {
    # Triads
    "maj": "Major",
    "min": "Minor",
    "dim": "Diminished",
    "aug": "Augmented",
    "sus2": "Suspended 2nd",
    "sus4": "Suspended 4th",
    # Sevenths
    "maj7": "Major 7th",
    "min7": "Minor 7th",
    "7": "Dominant 7th",
    "dim7": "Diminished 7th",
    "m7b5": "Half-Diminished 7th",
    "minmaj7": "Minor Major 7th",
    "aug7": "Augmented 7th",
    "augmaj7": "Augmented Major 7th",
    # Extended
    "9": "Dominant 9th",
    "maj9": "Major 9th",
    "min9": "Minor 9th",
    "11": "Dominant 11th",
    "min11": "Minor 11th",
    "13": "Dominant 13th",
    "min13": "Minor 13th",
    # Altered
    "7b5": "Dominant 7♭5",
    "7#5": "Dominant 7♯5",
    "7b9": "Dominant 7♭9",
    "7#9": "Dominant 7♯9",
    "add9": "Add 9",
    "madd9": "Minor Add 9",
    "6": "Major 6th",
    "min6": "Minor 6th",
    # Power chord
    "5": "Power Chord",
}

@dataclass(frozen=True)
class Chord:
    """Represents a chord: root pitch class + quality."""
    root: int          # 0-11
    quality: str       # key into CHORD_FORMULAS

    @classmethod
    def parse(cls, symbol: str) -> "Chord":
        """
        Parse chord symbol like 'Am', 'F#maj7', 'Bbm7b5', 'E7', 'Gsus4'.
        """
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("Empty chord symbol")

        # Extract root note (1 or 2 chars)
        if len(symbol) >= 2 and symbol[1] in ('#', 'b'):
            root_str = symbol[:2]
            rest = symbol[2:]
        else:
            root_str = symbol[:1]
            rest = symbol[1:]

        root = parse_note(root_str)

        # Determine quality from the remainder
        quality = _parse_quality(rest)
        return cls(root=root, quality=quality)

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        """Return the pitch classes (0-11) of all chord tones."""
        formula = CHORD_FORMULAS[self.quality]
        return tuple((self.root + interval) % 12 for interval in formula)

    @property
    def pitch_class_set(self) -> frozenset[int]:
        """Return unique pitch classes as a frozenset."""
        return frozenset(self.pitch_classes)

    @property
    def display_name(self) -> str:
        """Human-readable chord name, e.g. 'Am7', 'F#maj7'."""
        return note_name(self.root) + QUALITY_DISPLAY.get(self.quality, self.quality)

    @property
    def intervals(self) -> tuple[int, ...]:
        """Return the interval formula for this chord's quality."""
        return CHORD_FORMULAS[self.quality]

    def __str__(self) -> str:
        return self.display_name


def _parse_quality(s: str) -> str:
    """Map the suffix after the root note to a chord quality key."""
    if not s:
        return "maj"

    # Normalize common variations
    s_lower = s.lower()
    # Direct match first
    if s in CHORD_FORMULAS:
        return s
    if s_lower in CHORD_FORMULAS:
        return s_lower

    # Common aliases
    aliases = {
        "m": "min", "minor": "min", "-": "min",
        "M": "maj", "major": "maj", "Maj": "maj",
        "m7": "min7", "M7": "maj7", "Maj7": "maj7",
        "m7b5": "m7b5", "ø": "m7b5", "ø7": "m7b5",
        "o": "dim", "o7": "dim7", "°": "dim", "°7": "dim7",
        "+": "aug", "+7": "aug7",
        "dom7": "7", "dom": "7",
        "mmaj7": "minmaj7", "m(maj7)": "minmaj7", "mM7": "minmaj7",
        "m9": "min9", "m11": "min11", "m13": "min13",
        "m6": "min6", "m(add9)": "madd9",
    }
    if s in aliases:
        return aliases[s]
    if s_lower in aliases:
        return aliases[s_lower]

    raise ValueError(f"Unknown chord quality: '{s}'")


@dataclass
class ChordProgression:
    """An ordered sequence of chords with optional metadata."""
    chords: list[Chord] = field(default_factory=list)
    name: str = ""
    artist: str = ""
    key: str = ""

    @classmethod
    def parse(cls, symbols: list[str], **kwargs) -> "ChordProgression":
        """Parse a list of chord symbol strings."""
        chords = [Chord.parse(s) for s in symbols]
        return cls(chords=chords, **kwargs)

    @property
    def all_pitch_classes(self) -> frozenset[int]:
        """Union of all pitch classes across all chords."""
        pcs: set[int] = set()
        for chord in self.chords:
            pcs.update(chord.pitch_class_set)
        return frozenset(pcs)

    def display(self) -> str:
        return " - ".join(c.display_name for c in self.chords)

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "name": self.name,
            "artist": self.artist,
            "key": self.key,
            "chords": [c.display_name for c in self.chords],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChordProgression":
        """Deserialize from JSON."""
        chords = [Chord.parse(s) for s in d["chords"]]
        return cls(chords=chords, name=d.get("name", ""),
                   artist=d.get("artist", ""), key=d.get("key", ""))
