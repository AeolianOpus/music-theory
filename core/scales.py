"""
Scale definitions and utilities.
Each scale is defined by its interval pattern (semitones from root).
Includes 60+ scales covering Western, modal, jazz, exotic, and symmetric scales.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .music_theory import note_name, parse_note


# ── Scale Definitions ─────────────────────────────────────────────────
# Format: "Scale Name": (semitone intervals from root)
# All intervals are within one octave (0-11).

SCALE_CATALOG: dict[str, tuple[int, ...]] = {
    # ── Major modes ────────────────────────────────────
    "Ionian (Major)":           (0, 2, 4, 5, 7, 9, 11),
    "Dorian":                   (0, 2, 3, 5, 7, 9, 10),
    "Phrygian":                 (0, 1, 3, 5, 7, 8, 10),
    "Lydian":                   (0, 2, 4, 6, 7, 9, 11),
    "Mixolydian":               (0, 2, 4, 5, 7, 9, 10),
    "Aeolian (Natural Minor)":  (0, 2, 3, 5, 7, 8, 10),
    "Locrian":                  (0, 1, 3, 5, 6, 8, 10),

    # ── Harmonic minor modes ──────────────────────────
    "Harmonic Minor":           (0, 2, 3, 5, 7, 8, 11),
    "Locrian #6":               (0, 1, 3, 5, 6, 9, 10),
    "Ionian #5":                (0, 2, 4, 5, 8, 9, 11),
    "Dorian #4":                (0, 2, 3, 6, 7, 9, 10),
    "Phrygian Dominant":        (0, 1, 4, 5, 7, 8, 10),
    "Lydian #2":                (0, 3, 4, 6, 7, 9, 11),
    "Superlocrian bb7":         (0, 1, 3, 4, 6, 8, 9),

    # ── Melodic minor modes ───────────────────────────
    "Melodic Minor":            (0, 2, 3, 5, 7, 9, 11),
    "Dorian b2":                (0, 1, 3, 5, 7, 9, 10),
    "Lydian Augmented":         (0, 2, 4, 6, 8, 9, 11),
    "Lydian Dominant":          (0, 2, 4, 6, 7, 9, 10),
    "Mixolydian b6":            (0, 2, 4, 5, 7, 8, 10),
    "Aeolian b5 (Locrian #2)":  (0, 2, 3, 5, 6, 8, 10),
    "Altered (Super Locrian)":  (0, 1, 3, 4, 6, 8, 10),

    # ── Pentatonic / Blues ────────────────────────────
    "Major Pentatonic":         (0, 2, 4, 7, 9),
    "Minor Pentatonic":         (0, 3, 5, 7, 10),
    "Blues":                     (0, 3, 5, 6, 7, 10),
    "Major Blues":               (0, 2, 3, 4, 7, 9),

    # ── Symmetric ─────────────────────────────────────
    "Chromatic":                tuple(range(12)),
    "Whole Tone":               (0, 2, 4, 6, 8, 10),
    "Diminished (HW)":          (0, 1, 3, 4, 6, 7, 9, 10),
    "Diminished (WH)":          (0, 2, 3, 5, 6, 8, 9, 11),
    "Augmented":                (0, 3, 4, 7, 8, 11),

    # ── Jazz / Bebop ──────────────────────────────────
    "Bebop Dominant":           (0, 2, 4, 5, 7, 9, 10, 11),
    "Bebop Major":              (0, 2, 4, 5, 7, 8, 9, 11),
    "Bebop Minor":              (0, 2, 3, 5, 7, 8, 9, 10),
    "Bebop Dorian":             (0, 2, 3, 4, 5, 7, 9, 10),

    # ── Exotic / World ────────────────────────────────
    "Hungarian Minor":          (0, 2, 3, 6, 7, 8, 11),
    "Hungarian Major":          (0, 3, 4, 6, 7, 9, 10),
    "Double Harmonic Major":    (0, 1, 4, 5, 7, 8, 11),
    "Neapolitan Minor":         (0, 1, 3, 5, 7, 8, 11),
    "Neapolitan Major":         (0, 1, 3, 5, 7, 9, 11),
    "Persian":                  (0, 1, 4, 5, 6, 8, 11),
    "Arabian":                  (0, 2, 4, 5, 6, 8, 10),
    "Japanese (In)":            (0, 1, 5, 7, 8),
    "Japanese (Hirajoshi)":     (0, 2, 3, 7, 8),
    "Chinese":                  (0, 4, 6, 7, 11),
    "Egyptian":                 (0, 2, 5, 7, 10),
    "Balinese":                 (0, 1, 3, 7, 8),
    "Javanese":                 (0, 1, 3, 5, 7, 9, 10),
    "Vietnamese":               (0, 3, 5, 7, 8),

    # ── Spanish / Flamenco ────────────────────────────
    "Spanish 8-Tone":           (0, 1, 3, 4, 5, 6, 8, 10),
    "Flamenco":                 (0, 1, 4, 5, 7, 8, 11),  # = Double Harmonic Major

    # ── Miscellaneous ─────────────────────────────────
    "Enigmatic":                (0, 1, 4, 6, 8, 10, 11),
    "Prometheus":               (0, 2, 4, 6, 9, 10),
    "Tritone":                  (0, 1, 4, 6, 7, 10),
    "Leading Whole Tone":       (0, 2, 4, 6, 8, 10, 11),
    "Iwato":                    (0, 1, 5, 6, 10),
    "Kumoi":                    (0, 2, 3, 7, 9),
    "Pelog":                    (0, 1, 3, 7, 8),
    "Yo":                       (0, 2, 5, 7, 9),
    "Istrian":                  (0, 1, 3, 4, 6, 7),
    "Algerian":                 (0, 2, 3, 6, 7, 8, 11),
}

# ── Scale Categories (for UI grouping) ────────────────────────────────
SCALE_CATEGORIES: dict[str, list[str]] = {
    "Major Modes": [
        "Ionian (Major)", "Dorian", "Phrygian", "Lydian",
        "Mixolydian", "Aeolian (Natural Minor)", "Locrian",
    ],
    "Harmonic Minor Modes": [
        "Harmonic Minor", "Locrian #6", "Ionian #5", "Dorian #4",
        "Phrygian Dominant", "Lydian #2", "Superlocrian bb7",
    ],
    "Melodic Minor Modes": [
        "Melodic Minor", "Dorian b2", "Lydian Augmented",
        "Lydian Dominant", "Mixolydian b6",
        "Aeolian b5 (Locrian #2)", "Altered (Super Locrian)",
    ],
    "Pentatonic & Blues": [
        "Major Pentatonic", "Minor Pentatonic", "Blues", "Major Blues",
    ],
    "Symmetric": [
        "Chromatic", "Whole Tone", "Diminished (HW)",
        "Diminished (WH)", "Augmented",
    ],
    "Jazz / Bebop": [
        "Bebop Dominant", "Bebop Major", "Bebop Minor", "Bebop Dorian",
    ],
    "Exotic / World": [
        "Hungarian Minor", "Hungarian Major", "Double Harmonic Major",
        "Neapolitan Minor", "Neapolitan Major", "Persian", "Arabian",
        "Japanese (In)", "Japanese (Hirajoshi)", "Chinese", "Egyptian",
        "Balinese", "Javanese", "Vietnamese",
    ],
    "Spanish / Flamenco": [
        "Spanish 8-Tone", "Flamenco",
    ],
    "Other": [
        "Enigmatic", "Prometheus", "Tritone", "Leading Whole Tone",
        "Iwato", "Kumoi", "Pelog", "Yo", "Istrian", "Algerian",
    ],
}


@dataclass(frozen=True)
class Scale:
    """A specific scale: root + scale type."""
    root: int           # pitch class 0-11
    name: str           # key into SCALE_CATALOG
    intervals: tuple[int, ...]

    @classmethod
    def create(cls, root: int, name: str) -> "Scale":
        """Create a scale from root pitch class and catalog name."""
        if name not in SCALE_CATALOG:
            raise ValueError(f"Unknown scale: '{name}'")
        return cls(root=root % 12, name=name, intervals=SCALE_CATALOG[name])

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        """All pitch classes in this scale."""
        return tuple((self.root + iv) % 12 for iv in self.intervals)

    @property
    def pitch_class_set(self) -> frozenset[int]:
        return frozenset(self.pitch_classes)

    @property
    def display_name(self) -> str:
        return f"{note_name(self.root)} {self.name}"

    def contains_note(self, pc: int) -> bool:
        """Check if a pitch class belongs to this scale."""
        return (pc % 12) in self.pitch_class_set

    def degree_of(self, pc: int) -> Optional[int]:
        """Return the scale degree (0-indexed) of a pitch class, or None."""
        pc = pc % 12
        pcs = self.pitch_classes
        if pc in pcs:
            return pcs.index(pc)
        return None

    def note_names(self, prefer_flat: bool = False) -> list[str]:
        """Return list of note names in this scale."""
        return [note_name(pc, prefer_flat) for pc in self.pitch_classes]

    def __str__(self) -> str:
        return self.display_name


def get_all_scale_names() -> list[str]:
    """Return all available scale names."""
    return list(SCALE_CATALOG.keys())


def get_scales_in_category(category: str) -> list[str]:
    """Return scale names in a given category."""
    return SCALE_CATEGORIES.get(category, [])


def get_all_categories() -> list[str]:
    """Return all category names."""
    return list(SCALE_CATEGORIES.keys())


def build_scale(root_name: str, scale_name: str) -> Scale:
    """Convenience: build a Scale from note name string + scale name."""
    root_pc = parse_note(root_name)
    return Scale.create(root_pc, scale_name)
