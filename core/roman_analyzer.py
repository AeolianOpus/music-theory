"""
Roman numeral analysis for chord progressions.
Labels each chord with its function relative to a detected key.

Covers:
- Diatonic chords in major, minor, and modal contexts
- Harmonic-minor V in minor keys (tagged as "V (HM)")
- Secondary dominants — V/V and V/iv only
- Modal mixture / borrowed chords (bII, bIII, bVI, bVII, etc.)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .music_theory import Chord, ChordProgression, note_name
from .key_analyzer import KeyAnalysis, KeySection


@dataclass
class RomanLabel:
    """A single chord's function within a key."""
    chord: Chord
    numeral: str                    # display string: "i", "V (HM)", "bVI", "V/V", "?"
    function: str                   # "tonic", "predominant", "dominant", "borrowed", "secondary", "unknown"
    source: str                     # "diatonic", "harmonic_minor", "modal_mixture", "secondary_dominant", "unknown"
    scale_degree: Optional[int]     # 0-6 for diatonic chords; None for chromatic/unknown
    tooltip: str                    # short pro-level explanation
    
# ── Diatonic chord qualities per scale degree ────────────────────────
# For each mode, what's the natural triad quality on scale degrees 0-6?
# This is what lets us distinguish "ii" from "ii°" from "II".
#
# Format: ("maj" | "min" | "dim" | "aug", "uppercase" | "lowercase")
# The second element drives Roman numeral case: I vs i, V vs v.

_MAJOR = [
    ("maj", "I"),   ("min", "ii"),  ("min", "iii"), ("maj", "IV"),
    ("maj", "V"),   ("min", "vi"),  ("dim", "vii°"),
]

_NATURAL_MINOR = [
    ("min", "i"),   ("dim", "ii°"), ("maj", "III"), ("min", "iv"),
    ("min", "v"),   ("maj", "VI"),  ("maj", "VII"),
]

_DORIAN = [
    ("min", "i"),   ("min", "ii"),  ("maj", "III"), ("maj", "IV"),
    ("min", "v"),   ("dim", "vi°"), ("maj", "VII"),
]

_PHRYGIAN = [
    ("min", "i"),   ("maj", "II"),  ("maj", "III"), ("min", "iv"),
    ("dim", "v°"),  ("maj", "VI"),  ("min", "vii"),
]

_LYDIAN = [
    ("maj", "I"),   ("maj", "II"),  ("min", "iii"), ("dim", "iv°"),
    ("maj", "V"),   ("min", "vi"),  ("min", "vii"),
]

_MIXOLYDIAN = [
    ("maj", "I"),   ("min", "ii"),  ("dim", "iii°"),("maj", "IV"),
    ("min", "v"),   ("min", "vi"),  ("maj", "VII"),
]

_PHRYGIAN_DOMINANT = [
    ("maj", "I"),   ("maj", "II"),  ("dim", "iii°"),("min", "iv"),
    ("dim", "v°"),  ("maj", "VI"),  ("min", "vii"),
]

# Map Stage 1's mode names to these tables.
MODE_TABLES = {
    "Ionian (Major)":         _MAJOR,
    "Aeolian (Natural Minor)":_NATURAL_MINOR,
    "Dorian":                 _DORIAN,
    "Phrygian":               _PHRYGIAN,
    "Lydian":                 _LYDIAN,
    "Mixolydian":             _MIXOLYDIAN,
    "Phrygian Dominant":      _PHRYGIAN_DOMINANT,
    # Fallback: harmonic minor progressions get tagged via natural minor
    # and the HM-V detection handles the V chord specifically.
    "Harmonic Minor":         _NATURAL_MINOR,
    "Melodic Minor":          _NATURAL_MINOR,
    "Hungarian Minor":        _NATURAL_MINOR,
    "Locrian":                _NATURAL_MINOR,  # rare; fallback
}

# Labels for borrowed chords, indexed by semitone above tonic.
# Used when a chord doesn't fit the key but its root is still diatonically namable.
# Format: (uppercase_maj_label, lowercase_min_label, source_description)
_BORROWED_LABELS = {
    1:  ("bII",  "bii",  "from parallel Phrygian"),
    3:  ("bIII", "biii", "from parallel minor"),
    6:  ("bV",   "bv",   "tritone sub territory"),
    8:  ("bVI",  "bvi",  "from parallel minor"),
    10: ("bVII", "bvii", "from parallel minor (Mixolydian)"),
    # Raised degrees (less common but happen)
    2:  ("II",   "ii",   "from parallel Lydian / secondary"),
    4:  ("III",  "iii",  "from parallel major"),
    9:  ("VI",   "vi",   "from parallel major"),
    11: ("VII",  "vii",  "leading-tone / from parallel major"),
}

def _classify_chord_quality(chord: Chord) -> str:
    """
    Return a simplified quality bucket for comparison against diatonic tables.
    Returns 'maj', 'min', 'dim', 'aug', or 'other'.
    """
    q = chord.quality
    if q.startswith("min") or q in ("m7b5", "madd9"):
        return "min"
    if q in ("dim", "dim7"):
        return "dim"
    if q in ("aug", "augmaj7", "aug7"):
        return "aug"
    # Dominant and major both look "major" to the chord-degree table.
    # A G7 in C major is still V — the 7th is just coloration.
    if q in ("maj", "maj7", "maj9", "6", "add9",
             "7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9"):
        return "maj"
    # sus, power chords — treat as ambiguous/major for diatonic matching
    return "other"


def _is_dominant_quality(chord: Chord) -> bool:
    """True if the chord is major or dominant (i.e. could function as a V)."""
    return _classify_chord_quality(chord) == "maj"


def _has_seventh(chord: Chord) -> bool:
    """True if the chord includes a 7th (for V7 vs V distinction)."""
    return chord.quality in (
        "7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9",
        "maj7", "maj9", "min7", "min9", "min11", "min13",
        "dim7", "m7b5", "minmaj7", "aug7", "augmaj7",
    )


def analyze_roman(progression: ChordProgression,
                  key_analysis: KeyAnalysis) -> list[RomanLabel]:
    """
    Label each chord in the progression with its Roman numeral function.

    When key_analysis.sections contains multiple sections (the progression
    modulates), each chord is labeled relative to ITS section's key.
    For single-section input the behavior is identical to the original
    single-key analyzer.

    Args:
        progression: the chord progression to analyze
        key_analysis: the output of key_analyzer.analyze_key() or
                      modulation_detector.analyze_key_sections()

    Returns:
        A list of RomanLabel, one per chord, in progression order.
    """
    if not progression.chords or key_analysis is None:
        return []

    # Multi-section path: iterate sections, label each per its own key.
    # Single-section input falls through to this path too — it just runs
    # the loop body once, producing identical output to the original code.
    if key_analysis.sections and len(key_analysis.sections) > 1:
        return _analyze_roman_multi_section(progression, key_analysis)

    return _analyze_roman_single_key(progression, key_analysis)


def _analyze_roman_single_key(progression: ChordProgression,
                              key_analysis: KeyAnalysis) -> list[RomanLabel]:
    """Single-key Roman analysis. Original behavior, refactored into a
    helper so the multi-section path can reuse it per-section."""
    tonic_pc = key_analysis.tonic_pc
    mode_name = key_analysis.mode_name
    is_hm_v_system = key_analysis.scale_system == "harmonic_minor_V"

    # Look up the diatonic table for this mode.
    table = MODE_TABLES.get(mode_name, _MAJOR)

    # Parent scale pitch classes (for diatonic-chord-root detection).
    # The first scale in parent_scales is always the primary mode.
    parent_scale = key_analysis.parent_scales[0]

    # Build a map: scale_degree_pc -> (degree_index, expected_quality, numeral_text)
    degree_info: dict[int, tuple[int, str, str]] = {}
    for degree_idx, (expected_quality, numeral_text) in enumerate(table):
        degree_pc = parent_scale.pitch_classes[degree_idx]
        degree_info[degree_pc] = (degree_idx, expected_quality, numeral_text)

    labels: list[RomanLabel] = []
    for chord in progression.chords:
        labels.append(_label_one_chord(
            chord, tonic_pc, degree_info, is_hm_v_system, key_analysis,
        ))

    return labels


def _analyze_roman_multi_section(progression: ChordProgression,
                                 key_analysis: KeyAnalysis) -> list[RomanLabel]:
    """Per-section Roman analysis for modulating progressions.
    For each KeySection, build a single-section synthetic KeyAnalysis,
    slice the progression to the section's chord range, and run the
    single-key analyzer on that slice. Concatenate the per-section
    label lists in progression order.
    """
    # Local import to avoid a circular import at module load time
    # (modulation_detector imports from key_analyzer; we import the
    # helper from modulation_detector here only when actually needed).
    from .modulation_detector import slice_progression_to_section, build_section_analysis

    all_labels: list[RomanLabel] = []
    for section in key_analysis.sections:
        section_prog = slice_progression_to_section(progression, section)
        section_analysis = build_section_analysis(progression, section)
        if section_analysis is None:
            # Fallback: produce "?" labels for this section's chords
            for chord in section_prog.chords:
                all_labels.append(RomanLabel(
                    chord=chord,
                    numeral="?",
                    function="unknown",
                    source="unknown",
                    scale_degree=None,
                    tooltip=f"{chord.display_name} — section analysis failed",
                ))
            continue
        section_labels = _analyze_roman_single_key(section_prog, section_analysis)
        all_labels.extend(section_labels)

    return all_labels


def _label_one_chord(chord: Chord,
                     tonic_pc: int,
                     degree_info: dict[int, tuple[int, str, str]],
                     is_hm_v_system: bool,
                     key_analysis: KeyAnalysis) -> RomanLabel:
    """Produce a RomanLabel for a single chord."""
    chord_quality = _classify_chord_quality(chord)
    interval_from_tonic = (chord.root - tonic_pc) % 12
    
    # ── Case 1: chord root is diatonic to the key ──
    if chord.root in degree_info:
        degree_idx, expected_quality, numeral_text = degree_info[chord.root]
        
        # ── Case 1a: harmonic-minor V (V or V7 in a minor key) ──
        # This takes precedence over plain diatonic when Stage 1 flagged the system.
        if (is_hm_v_system
                and degree_idx == 4                  # scale degree 5 (V)
                and chord_quality == "maj"           # major or dominant-7 quality
                and expected_quality == "min"):      # but the mode expected minor (v)
            numeral = "V7 (HM)" if _has_seventh(chord) else "V (HM)"
            return RomanLabel(
                chord=chord,
                numeral=numeral,
                function="dominant",
                source="harmonic_minor",
                scale_degree=4,
                tooltip=f"{numeral} — dominant, borrowed from harmonic minor\n"
                        f"raised 7th: {note_name((tonic_pc + 11) % 12)}",
            )
        
        # ── Case 1b: quality matches the diatonic expectation ──
        if chord_quality == expected_quality or (chord_quality == "maj" and expected_quality == "maj"):
            # Append 7 for dominant-7 V chords (common convention)
            display_numeral = numeral_text
            if _has_seventh(chord) and numeral_text == "V":
                display_numeral = "V7"
            function = _degree_to_function(degree_idx, numeral_text)
            return RomanLabel(
                chord=chord,
                numeral=display_numeral,
                function=function,
                source="diatonic",
                scale_degree=degree_idx,
                tooltip=f"{display_numeral} — {function}",
            )
        
        # ── Case 1c: root is diatonic but quality is altered ──
        # Example: C major getting a Dm → D7 (V/V). We let Case 2 handle it
        # below by falling through.
    
    # ── Case 2: secondary dominant (V/V or V/iv) ──
    # The chord must be major/dominant quality, and its resolution target
    # (perfect 4th above) must be either V or iv of the key.
    if chord_quality == "maj":
        resolution_pc = (chord.root + 5) % 12  # perfect 4th up
        if resolution_pc in degree_info:
            target_degree, target_quality, target_numeral = degree_info[resolution_pc]
            
            if target_degree == 4:  # V of key → V/V
                display = "V7/V" if _has_seventh(chord) else "V/V"
                return RomanLabel(
                    chord=chord,
                    numeral=display,
                    function="secondary",
                    source="secondary_dominant",
                    scale_degree=None,
                    tooltip=f"{display} — dominant of {target_numeral}\n"
                            f"tonicizes the {target_numeral} chord",
                )
            
            if target_degree == 3 and target_quality == "min":  # iv of minor key → V/iv
                display = "V7/iv" if _has_seventh(chord) else "V/iv"
                return RomanLabel(
                    chord=chord,
                    numeral=display,
                    function="secondary",
                    source="secondary_dominant",
                    scale_degree=None,
                    tooltip=f"{display} — dominant of {target_numeral}\n"
                            f"tonicizes the {target_numeral} chord",
                )
    
    # ── Case 3: borrowed / modal mixture ──
    # Root is chromatic to the key. Use flat-numeral convention.
    if interval_from_tonic in _BORROWED_LABELS:
        upper, lower, source_desc = _BORROWED_LABELS[interval_from_tonic]
        # Pick case based on chord quality
        numeral = upper if chord_quality in ("maj", "aug") else lower
        if chord_quality == "dim":
            numeral = numeral + "°"
        return RomanLabel(
            chord=chord,
            numeral=numeral,
            function="borrowed",
            source="modal_mixture",
            scale_degree=None,
            tooltip=f"{numeral} — {source_desc}",
        )
    
    # ── Case 4: unknown (shouldn't happen for single chords but safe fallback) ──
    return RomanLabel(
        chord=chord,
        numeral="?",
        function="unknown",
        source="unknown",
        scale_degree=None,
        tooltip=f"{chord.display_name} — outside the detected key",
    )


def _degree_to_function(degree_idx: int, numeral: str) -> str:
    """Map scale degree (0-6) to harmonic function."""
    # degree_idx is 0-indexed: 0=I, 3=IV, 4=V, etc.
    if degree_idx == 0:
        return "tonic"
    if degree_idx == 4:
        return "dominant"
    if degree_idx in (1, 3):  # ii, IV / iv
        return "predominant"
    if degree_idx == 6 and numeral.startswith("v"):  # vii° in major
        return "dominant"  # leading-tone, functions as dominant
    # iii, vi, III, VI, VII and friends — tonic-substitute territory
    return "tonic-substitute"