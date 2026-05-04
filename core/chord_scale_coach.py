"""
Per-chord scale coach.

For each chord in a progression, suggests scales to solo over.
Combines chord-specific harmonic logic with idiomatic style tags
(rock_blues, jazz, neoclassical, fusion, universal) so a player can
quickly find the option that matches what they're going for.

Inputs: a ChordProgression, the KeyAnalysis from key_analyzer, and the
RomanLabel list from roman_analyzer. Each chord gets back up to 5
ranked ChordScaleOption objects.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .music_theory import Chord, ChordProgression, note_name
from .scales import Scale
from .key_analyzer import KeyAnalysis
from .roman_analyzer import RomanLabel


# Idiom tags used in ChordScaleOption.idioms.
# Keep this list small and stable — UI may filter on these strings.
IDIOM_ROCK_BLUES = "rock_blues"
IDIOM_JAZZ = "jazz"
IDIOM_NEOCLASSICAL = "neoclassical"
IDIOM_FUSION = "fusion"
IDIOM_UNIVERSAL = "universal"  # works in any context — pentatonics, diatonic modes


@dataclass
class ChordScaleOption:
    """A single scale suggestion for soloing over a chord."""
    scale: Scale
    fit: str                    # "perfect" | "tension" | "color"
    reason: str                 # short pro-level: "V — Yngwie's choice"
    priority: int               # 0=primary, 1=secondary, 2=outside/color
    idioms: list[str]           # which styles this option is idiomatic in


@dataclass
class ChordScaleAdvice:
    """Scale options for a single chord in a progression."""
    chord: Chord
    options: list[ChordScaleOption] = field(default_factory=list)
    
# ── Helper: build a ChordScaleOption tersely ─────────────────────────────

def _opt(scale: Scale,
         fit: str,
         reason: str,
         priority: int,
         idioms: list[str]) -> ChordScaleOption:
    """Compact constructor — saves lots of vertical space in the suggestion tables."""
    return ChordScaleOption(
        scale=scale, fit=fit, reason=reason,
        priority=priority, idioms=idioms,
    )


def _has_seventh(chord: Chord) -> bool:
    """True if the chord has a 7th (dominant or otherwise)."""
    return chord.quality in (
        "7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9",
        "maj7", "maj9", "min7", "min9", "min11", "min13",
        "dim7", "m7b5", "minmaj7", "aug7", "augmaj7",
    )


def _is_minor_quality(chord: Chord) -> bool:
    """True if chord is minor-flavored (for picking pent + scale defaults)."""
    return chord.quality.startswith("min") or chord.quality in (
        "m7b5", "dim", "dim7", "madd9",
    )
    
# ── Suggestion functions per Roman function ───────────────────────────
#
# Each function takes the chord, key analysis, and roman label,
# returns a list of ChordScaleOption sorted by priority (caller may trim to 5).
#
# Naming convention: _suggest_<function>(chord, ka, rl) -> list[ChordScaleOption]
# A central dispatcher routes Roman labels to these.


def _suggest_tonic(chord: Chord, ka: KeyAnalysis,
                   rl: RomanLabel) -> list[ChordScaleOption]:
    """Tonic chord (i, I). The home base — most options live here."""
    opts: list[ChordScaleOption] = []
    is_minor = _is_minor_quality(chord)
    root = chord.root  # tonic chord root = key tonic

    if is_minor:
        opts.append(_opt(
            Scale.create(root, "Minor Pentatonic"),
            "perfect", "i — universal pentatonic box",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(root, "Aeolian (Natural Minor)"),
            "perfect", "i — natural minor (diatonic)",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES, IDIOM_NEOCLASSICAL],
        ))
        # Blues scale on the tonic, regardless of progression context.
        opts.append(_opt(
            Scale.create(root, "Blues"),
            "color", "i — blues scale, b5 as passing tone",
            0, [IDIOM_ROCK_BLUES],
        ))
        # Harmonic minor only if the progression actually has the HM-V system.
        if ka.scale_system == "harmonic_minor_V":
            opts.append(_opt(
                Scale.create(root, "Harmonic Minor"),
                "perfect", "i — harmonic minor (matches V chord)",
                0, [IDIOM_NEOCLASSICAL, IDIOM_FUSION],
            ))
        # Dorian if the progression uses major IV (Dorian's signature)
        if ka.mode_name == "Dorian":
            opts.append(_opt(
                Scale.create(root, "Dorian"),
                "perfect", "i — Dorian (major IV in progression)",
                0, [IDIOM_UNIVERSAL, IDIOM_FUSION, IDIOM_JAZZ],
            ))
        opts.append(_opt(
            Scale.create(root, "Melodic Minor"),
            "tension", "i — melodic minor (jazz minor)",
            1, [IDIOM_JAZZ, IDIOM_FUSION],
        ))
        opts.append(_opt(
            Scale.create(root, "Hungarian Minor"),
            "color", "i — exotic minor (raised 4th)",
            2, [IDIOM_NEOCLASSICAL],
        ))
    else:
        # Major tonic
        opts.append(_opt(
            Scale.create(root, "Major Pentatonic"),
            "perfect", "I — major pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(root, "Ionian (Major)"),
            "perfect", "I — major scale (diatonic)",
            0, [IDIOM_UNIVERSAL, IDIOM_JAZZ],
        ))
        opts.append(_opt(
            Scale.create(root, "Major Blues"),
            "color", "I — major blues scale",
            0, [IDIOM_ROCK_BLUES],
        ))
        # Mixolydian if the key actually has bVII borrows (or is Mixolydian)
        if ka.mode_name == "Mixolydian":
            opts.append(_opt(
                Scale.create(root, "Mixolydian"),
                "perfect", "I — Mixolydian (b7 in progression)",
                0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES, IDIOM_FUSION],
            ))
        elif ka.mode_name == "Lydian":
            opts.append(_opt(
                Scale.create(root, "Lydian"),
                "perfect", "I — Lydian (#4 in progression)",
                0, [IDIOM_FUSION, IDIOM_JAZZ],
            ))
        opts.append(_opt(
            Scale.create(root, "Lydian"),
            "color", "I — Lydian (bright #4 color)",
            1, [IDIOM_JAZZ, IDIOM_FUSION],
        ))
    return opts


def _suggest_dominant(chord: Chord, ka: KeyAnalysis,
                      rl: RomanLabel) -> list[ChordScaleOption]:
    """V or V7 (diatonic dominant). Distinct from V (HM) — see _suggest_v_hm."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root
    key_tonic = ka.tonic_pc

    opts.append(_opt(
        Scale.create(chord_root, "Mixolydian"),
        "perfect", "V — Mixolydian (chord-tone scale)",
        0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES, IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(key_tonic, "Major Pentatonic"),
        "perfect", "V — key's major pent (safe over the whole progression)",
        0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Minor Pentatonic"),
        "perfect", "V — chord-root minor pent (bluesy)",
        0, [IDIOM_ROCK_BLUES],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Altered (Super Locrian)"),
        "tension", "V — altered (jazz tension over V7)",
        1, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Diminished (HW)"),
        "tension", "V — half-whole dim (b9, #9, #11)",
        1, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Lydian Dominant"),
        "color", "V — Lydian dominant (#11)",
        2, [IDIOM_FUSION, IDIOM_JAZZ],
    ))
    return opts


def _suggest_v_hm(chord: Chord, ka: KeyAnalysis,
                  rl: RomanLabel) -> list[ChordScaleOption]:
    """V (HM) — V chord with raised 7th from harmonic minor. Yngwie territory."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root
    key_tonic = ka.tonic_pc

    opts.append(_opt(
        Scale.create(key_tonic, "Harmonic Minor"),
        "perfect", "V (HM) — key's harmonic minor",
        0, [IDIOM_NEOCLASSICAL, IDIOM_UNIVERSAL],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Phrygian Dominant"),
        "perfect", "V (HM) — Phrygian dominant (Yngwie's choice)",
        0, [IDIOM_NEOCLASSICAL, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(key_tonic, "Hungarian Minor"),
        "color", "V (HM) — Hungarian minor (extra exotic)",
        1, [IDIOM_NEOCLASSICAL],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Altered (Super Locrian)"),
        "tension", "V (HM) — altered (jazz substitute)",
        1, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Diminished (HW)"),
        "tension", "V (HM) — half-whole dim",
        2, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    return opts


def _suggest_predominant(chord: Chord, ka: KeyAnalysis,
                         rl: RomanLabel) -> list[ChordScaleOption]:
    """ii, IV, iv chords. Lead-into-V flavor."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root
    key_tonic = ka.tonic_pc
    is_minor = _is_minor_quality(chord)

    if is_minor:
        # ii in major or iv in minor
        opts.append(_opt(
            Scale.create(chord_root, "Dorian"),
            "perfect", f"{rl.numeral} — Dorian (chord's natural mode)",
            0, [IDIOM_UNIVERSAL, IDIOM_JAZZ, IDIOM_FUSION],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Minor Pentatonic"),
            "perfect", f"{rl.numeral} — minor pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Aeolian (Natural Minor)"),
            "perfect", f"{rl.numeral} — natural minor",
            0, [IDIOM_UNIVERSAL, IDIOM_NEOCLASSICAL],
        ))
        opts.append(_opt(
            Scale.create(key_tonic,
                         "Aeolian (Natural Minor)" if ka.tonic_name in ka.display
                         and "minor" in ka.display else "Ionian (Major)"),
            "perfect", f"{rl.numeral} — key's parent scale",
            1, [IDIOM_UNIVERSAL],
        ))
    else:
        # IV in major
        opts.append(_opt(
            Scale.create(chord_root, "Lydian"),
            "perfect", f"{rl.numeral} — Lydian (chord's natural mode)",
            0, [IDIOM_UNIVERSAL, IDIOM_JAZZ, IDIOM_FUSION],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Major Pentatonic"),
            "perfect", f"{rl.numeral} — major pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Ionian (Major)"),
            "perfect", f"{rl.numeral} — major scale",
            0, [IDIOM_UNIVERSAL],
        ))
        opts.append(_opt(
            Scale.create(key_tonic, "Ionian (Major)"),
            "perfect", f"{rl.numeral} — key's major scale",
            1, [IDIOM_UNIVERSAL],
        ))
    return opts


def _suggest_secondary(chord: Chord, ka: KeyAnalysis,
                       rl: RomanLabel) -> list[ChordScaleOption]:
    """V/V or V/iv — secondary dominant. Treat like a temporary V7."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root

    opts.append(_opt(
        Scale.create(chord_root, "Mixolydian"),
        "perfect", f"{rl.numeral} — Mixolydian (sets up the resolution)",
        0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES, IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Major Pentatonic"),
        "perfect", f"{rl.numeral} — major pentatonic",
        0, [IDIOM_ROCK_BLUES],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Minor Pentatonic"),
        "perfect", f"{rl.numeral} — minor pent (bluesy V)",
        0, [IDIOM_ROCK_BLUES],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Altered (Super Locrian)"),
        "tension", f"{rl.numeral} — altered (jazz tension)",
        1, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    opts.append(_opt(
        Scale.create(chord_root, "Lydian Dominant"),
        "color", f"{rl.numeral} — Lydian dominant (#11)",
        2, [IDIOM_FUSION, IDIOM_JAZZ],
    ))
    return opts


def _suggest_borrowed(chord: Chord, ka: KeyAnalysis,
                      rl: RomanLabel) -> list[ChordScaleOption]:
    """bIII, bVI, bVII, etc. — modal mixture from parallel mode."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root
    is_minor = _is_minor_quality(chord)

    if is_minor:
        opts.append(_opt(
            Scale.create(chord_root, "Aeolian (Natural Minor)"),
            "perfect", f"{rl.numeral} — natural minor (parallel mode)",
            0, [IDIOM_UNIVERSAL],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Minor Pentatonic"),
            "perfect", f"{rl.numeral} — minor pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Dorian"),
            "color", f"{rl.numeral} — Dorian (brighter borrowing)",
            1, [IDIOM_FUSION, IDIOM_JAZZ],
        ))
    else:
        # Borrowed major chord (bIII, bVI, bVII typically)
        opts.append(_opt(
            Scale.create(chord_root, "Ionian (Major)"),
            "perfect", f"{rl.numeral} — major scale (parallel mode)",
            0, [IDIOM_UNIVERSAL],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Major Pentatonic"),
            "perfect", f"{rl.numeral} — major pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Lydian"),
            "color", f"{rl.numeral} — Lydian (bright #4)",
            1, [IDIOM_FUSION, IDIOM_JAZZ],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Mixolydian"),
            "color", f"{rl.numeral} — Mixolydian (b7 color)",
            1, [IDIOM_ROCK_BLUES, IDIOM_FUSION],
        ))
    return opts


def _suggest_substitute(chord: Chord, ka: KeyAnalysis,
                        rl: RomanLabel) -> list[ChordScaleOption]:
    """iii, vi, III, VI, VII — tonic-substitute color chords."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root
    key_tonic = ka.tonic_pc
    is_minor = _is_minor_quality(chord)

    if is_minor:
        opts.append(_opt(
            Scale.create(chord_root, "Minor Pentatonic"),
            "perfect", f"{rl.numeral} — minor pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Aeolian (Natural Minor)"),
            "perfect", f"{rl.numeral} — natural minor",
            0, [IDIOM_UNIVERSAL],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Dorian"),
            "perfect", f"{rl.numeral} — Dorian (jazz default for minor)",
            1, [IDIOM_JAZZ, IDIOM_FUSION],
        ))
    else:
        opts.append(_opt(
            Scale.create(chord_root, "Major Pentatonic"),
            "perfect", f"{rl.numeral} — major pentatonic",
            0, [IDIOM_UNIVERSAL, IDIOM_ROCK_BLUES],
        ))
        opts.append(_opt(
            Scale.create(chord_root, "Ionian (Major)"),
            "perfect", f"{rl.numeral} — major scale",
            0, [IDIOM_UNIVERSAL],
        ))
    # Always include the key's parent scale as fallback context.
    parent_scale_name = ka.parent_scales[0].name if ka.parent_scales else "Ionian (Major)"
    opts.append(_opt(
        Scale.create(key_tonic, parent_scale_name),
        "perfect", f"{rl.numeral} — key's parent scale",
        1, [IDIOM_UNIVERSAL],
    ))
    return opts


def _suggest_unknown(chord: Chord, ka: KeyAnalysis,
                     rl: RomanLabel) -> list[ChordScaleOption]:
    """Chromatic chord we couldn't classify. Suggest chord-tone arpeggio + chromatic."""
    opts: list[ChordScaleOption] = []
    chord_root = chord.root

    # No "arpeggio scale" exists in the catalog — use the chord's pentatonic as fallback.
    if _is_minor_quality(chord):
        opts.append(_opt(
            Scale.create(chord_root, "Minor Pentatonic"),
            "perfect", f"{chord.display_name} — chord-root minor pent (safe)",
            0, [IDIOM_UNIVERSAL],
        ))
    else:
        opts.append(_opt(
            Scale.create(chord_root, "Major Pentatonic"),
            "perfect", f"{chord.display_name} — chord-root major pent (safe)",
            0, [IDIOM_UNIVERSAL],
        ))
    opts.append(_opt(
        Scale.create(chord_root, "Chromatic"),
        "color", f"{chord.display_name} — chromatic (use chord tones as anchors)",
        2, [IDIOM_JAZZ, IDIOM_FUSION],
    ))
    return opts

# ── Dispatch ──────────────────────────────────────────────────────────


# Map Roman label functions/sources to suggestion builders.
# Order of resolution: source overrides function. Specifically, "harmonic_minor"
# source on a dominant chord routes to _suggest_v_hm, not _suggest_dominant.
def _route(rl: RomanLabel):
    """Pick the suggestion function for a Roman label."""
    if rl.source == "harmonic_minor":
        return _suggest_v_hm
    if rl.source == "secondary_dominant":
        return _suggest_secondary
    if rl.source == "modal_mixture":
        return _suggest_borrowed
    if rl.function == "tonic":
        return _suggest_tonic
    if rl.function == "dominant":
        return _suggest_dominant
    if rl.function == "predominant":
        return _suggest_predominant
    if rl.function == "tonic-substitute":
        return _suggest_substitute
    return _suggest_unknown


def analyze_chord_scales(
    progression: ChordProgression,
    key_analysis: Optional[KeyAnalysis],
    roman_labels: list[RomanLabel],
    max_options: int = 5,
) -> list[ChordScaleAdvice]:
    """
    Produce per-chord scale advice for the whole progression.

    Args:
        progression: chord progression to analyze.
        key_analysis: output of analyze_key(). May be None for empty progressions.
        roman_labels: output of analyze_roman(); must be same length as progression.chords.
        max_options: cap on options per chord (default 5).

    Returns:
        One ChordScaleAdvice per chord, in progression order.
    """
    if not progression.chords or key_analysis is None:
        return []
    if len(roman_labels) != len(progression.chords):
        raise ValueError(
            f"roman_labels length ({len(roman_labels)}) must match "
            f"progression.chords length ({len(progression.chords)})"
        )

    # If the whole progression is dominant-7's (blues context), add the blues
    # scale to every chord. Detected via Stage 1's all-dominants implicit check:
    # when the key system is "chromatic" AND every chord is dominant-quality,
    # we treat it as blues context.
    DOMINANT_QUALITIES = ("7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9", "aug7")
    is_blues_context = (
        len(progression.chords) >= 2
        and all(c.quality in DOMINANT_QUALITIES for c in progression.chords)
    )

    advice_list: list[ChordScaleAdvice] = []
    for chord, rl in zip(progression.chords, roman_labels):
        builder = _route(rl)
        opts = builder(chord, key_analysis, rl)

        # Inject blues scale on every chord in a blues context
        # (it's only on tonic by default in non-blues keys).
        if is_blues_context:
            opts.append(_opt(
                Scale.create(chord.root, "Blues"),
                "color", f"{chord.display_name} — blues scale (blues context)",
                0, [IDIOM_ROCK_BLUES],
            ))

        # Sort by priority ascending, then by fit (perfect > tension > color),
        # so the most reachable options come first.
        FIT_RANK = {"perfect": 0, "tension": 1, "color": 2}
        opts.sort(key=lambda o: (o.priority, FIT_RANK.get(o.fit, 3)))

        # Cap at max_options.
        opts = opts[:max_options]

        advice_list.append(ChordScaleAdvice(chord=chord, options=opts))

    return advice_list