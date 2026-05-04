"""
Music-theoretic key and mode analysis for chord progressions.
Detects tonic, mode, and handles common mode-mixing patterns
(especially harmonic-minor V in natural minor keys).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .music_theory import ChordProgression, Chord, note_name
from .scales import Scale, SCALE_CATALOG


# Parent scales to check for mode detection (7-note diatonic scales only)
MODE_SCALES = (
    "Ionian (Major)",
    "Aeolian (Natural Minor)",
    "Dorian",
    "Phrygian",
    "Lydian",
    "Mixolydian",
    "Locrian",
    "Harmonic Minor",
    "Melodic Minor",
    "Phrygian Dominant",
    "Hungarian Minor",
)

# Friendly mode labels
MODE_LABELS = {
    "Ionian (Major)": "major",
    "Aeolian (Natural Minor)": "minor",
    "Dorian": "Dorian",
    "Phrygian": "Phrygian",
    "Lydian": "Lydian",
    "Mixolydian": "Mixolydian",
    "Locrian": "Locrian",
    "Harmonic Minor": "harmonic minor",
    "Melodic Minor": "melodic minor",
    "Phrygian Dominant": "Phrygian Dominant",
    "Hungarian Minor": "Hungarian minor",
}


@dataclass
class KeyAnalysis:
    """Result of analyzing a chord progression."""
    tonic_pc: int                          # pitch class of tonic (0-11)
    tonic_name: str                        # "F#", "A", etc.
    mode_name: str                         # "Aeolian (Natural Minor)", etc.
    mode_label: str                        # friendly label like "minor"
    scale_system: str                      # "pure", "harmonic_minor_V", "chromatic"
    parent_scales: list[Scale]             # scales that together cover the progression
    confidence: float                      # 0.0-1.0
    display: str                           # e.g. "F# minor (harmonic minor V)"
    notes: list[str] = field(default_factory=list)  # human-readable explanations


def _find_tonic(progression: ChordProgression) -> Optional[tuple[int, str]]:
    """
    Identify the likely tonic and its quality (major/minor).

    Uses multiple heuristics:
    - First and last chords are weighted higher (they bookend the progression)
    - Minor and major triads (stable chord qualities) weight higher than dominants
    - Dominant 7th chords at cadence points are treated as V chords — their resolution
    target (a perfect 4th above) gets credit instead of the chord itself
    - Chord repetition in the progression reinforces tonic candidacy

    Returns (pitch_class, quality) or None if progression is empty.
    """
    if not progression.chords:
        return None

    scores: dict[int, float] = {}
    quality_votes: dict[int, dict[str, float]] = {}  # pc -> {"minor": x, "major": y}
    n = len(progression.chords)

    def _add_vote(pc: int, weight: float, quality: str) -> None:
        scores[pc] = scores.get(pc, 0.0) + weight
        if pc not in quality_votes:
            quality_votes[pc] = {"minor": 0.0, "major": 0.0}
        quality_votes[pc][quality] = quality_votes[pc].get(quality, 0.0) + weight

    def _classify_quality(chord: Chord) -> str:
        """Return 'minor', 'major', or 'ambiguous'."""
        q = chord.quality
        if q.startswith("min") or q in ("m7b5", "dim", "dim7", "madd9"):
            return "minor"
        if q in ("maj", "maj7", "maj9", "6", "add9", "aug", "augmaj7"):
            return "major"
        if q in ("7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9", "aug7"):
            return "dominant"  # treated specially below
        if q in ("sus2", "sus4", "5"):
            return "ambiguous"
        return "ambiguous"

    # Detect "all-dominants" context (blues, static dominant vamp, Mixolydian riff).
    # If every chord is a dominant 7, no chord is acting as a V→I resolution — they're
    # all stable tonics in their local context. Disable resolution-target voting.
    all_dominants = (
        len(progression.chords) >= 2
        and all(_classify_quality(c) == "dominant" for c in progression.chords)
    )
    
    for i, chord in enumerate(progression.chords):
        # Position-based weight
        if i == 0:
            position_weight = 2.5  # first chord — tonic in looping progressions
        elif i == n - 1:
            position_weight = 2.5  # last chord — tonic at cadence
        else:
            position_weight = 1.0

        quality_type = _classify_quality(chord)

        # Dominant 7th / strong dominant chords: vote for their RESOLUTION target, not themselves
        # The resolution target of a V chord is a perfect 5th below (= perfect 4th above in octave)
        if quality_type == "dominant":
            # Blues/vamp context: dominant IS the tonic (blues I chord is dominant-quality).
            # Also: a dominant 7 as the FIRST chord is almost always the tonic of a
            # dominant-flavored context, not a V that resolves forward.
            if all_dominants or i == 0:
                _add_vote(chord.root, position_weight * 1.5, "major")
            else:
                resolution_pc = (chord.root + 5) % 12  # perfect 4th up = resolution target
                # The resolution is probably minor (common case: V7 → i in minor key)
                # But could also be major (V7 → I). We vote for both and let cadence sort it out.
                _add_vote(resolution_pc, position_weight * 1.2, "minor")
                _add_vote(resolution_pc, position_weight * 0.8, "major")
                # The chord itself gets a small vote (could be tonic of a blues vamp)
                _add_vote(chord.root, position_weight * 0.3, "major")

        elif quality_type == "minor":
            # Minor triads are strong tonic candidates (you play mostly minor keys)
            _add_vote(chord.root, position_weight * 1.5, "minor")

        elif quality_type == "major":
            # Major triads are stable tonic candidates too
            _add_vote(chord.root, position_weight * 1.2, "major")

        else:  # ambiguous (sus, power chords)
            _add_vote(chord.root, position_weight, "major")

    # Pick highest-scoring pitch class
    best_root = max(scores, key=lambda k: scores[k])

    # Determine quality based on which quality accumulated more votes on that root
    votes = quality_votes.get(best_root, {"minor": 0.0, "major": 0.0})
    if votes["minor"] >= votes["major"]:
        return (best_root, "minor")
    else:
        return (best_root, "major")


def _is_dominant_of_tonic(chord: Chord, tonic_pc: int) -> bool:
    """
    Check if a chord is the dominant (V) of the given tonic.
    A dominant is a major chord (or dominant 7th) a perfect 5th above the tonic.
    """
    if (chord.root - tonic_pc) % 12 != 7:
        return False
    return chord.quality in (
        "maj", "7", "maj7", "9", "maj9", "11", "13",
        "7b5", "7#5", "7b9", "7#9", "aug", "aug7", "augmaj7", "add9", "6",
    )


def _coverage(chord_pcs: frozenset[int], scale: Scale) -> float:
    """Fraction of chord pitch classes contained in scale."""
    if not chord_pcs:
        return 0.0
    return len(chord_pcs & scale.pitch_class_set) / len(chord_pcs)


def analyze_key(progression: ChordProgression) -> Optional[KeyAnalysis]:
    """
    Full key analysis of a chord progression.
    Returns None if the progression is empty.
    """
    if not progression.chords:
        return None
    
    tonic_info = _find_tonic(progression)
    if tonic_info is None:
        return None
    tonic_pc, tonic_quality = tonic_info
    tonic_name = note_name(tonic_pc)
    
    # Split chords: dominant-function vs everything else
    dominant_chords = [c for c in progression.chords if _is_dominant_of_tonic(c, tonic_pc)]
    non_dominant_chords = [c for c in progression.chords if not _is_dominant_of_tonic(c, tonic_pc)]
    
    # Gather pitch classes
    non_dom_pcs: frozenset[int] = frozenset()
    for c in non_dominant_chords:
        non_dom_pcs = non_dom_pcs | c.pitch_class_set
    
    all_pcs = progression.all_pitch_classes
    
    # Find best-fitting mode for the tonic (filtered by tonic quality)
    # If tonic is minor, only consider minor-flavored modes; same for major
    if tonic_quality == "minor":
        candidate_modes = (
            "Aeolian (Natural Minor)",
            "Dorian",
            "Phrygian",
            "Harmonic Minor",
            "Melodic Minor",
            "Hungarian Minor",
            "Locrian",
        )
    else:
        candidate_modes = (
            "Ionian (Major)",
            "Lydian",
            "Mixolydian",
            "Phrygian Dominant",  # major 3rd despite Phrygian name
        )
    
    # Rank modes by coverage of NON-dominant chord pitch classes
    mode_fits: list[tuple[str, Scale, float, float]] = []
    for mode_name in candidate_modes:
        scale = Scale.create(tonic_pc, mode_name)
        non_dom_cov = _coverage(non_dom_pcs, scale) if non_dom_pcs else 1.0
        full_cov = _coverage(all_pcs, scale)
        mode_fits.append((mode_name, scale, non_dom_cov, full_cov))
    
    # Sort: prefer highest non-dominant coverage, then highest full coverage
    mode_fits.sort(key=lambda x: (-x[2], -x[3]))
    best_mode_name, best_mode_scale, best_non_dom_cov, best_full_cov = mode_fits[0]
    
    # "Natural minor + harmonic V" correction:
    # When a progression contains a dominant V, harmonic minor often ties with natural
    # minor on coverage because harmonic minor is a superset of the notes actually used
    # (the differing 6th/7th happen to not appear in the non-V chords). The more honest
    # musical description is "natural minor borrowing V from harmonic minor" — that's
    # how a working musician thinks about it. So if the winner is a harmonic/melodic
    # minor variant AND natural minor would also cover the non-V chords, switch to
    # natural minor and let the harmonic-minor-V logic below tag the borrowing.
    if (
        tonic_quality == "minor"
        and dominant_chords
        and best_mode_name in ("Harmonic Minor", "Melodic Minor", "Hungarian Minor")
    ):
        aeolian = Scale.create(tonic_pc, "Aeolian (Natural Minor)")
        non_dom_cov_aeolian = _coverage(non_dom_pcs, aeolian) if non_dom_pcs else 1.0
        if non_dom_cov_aeolian >= 0.99:
            best_mode_name = "Aeolian (Natural Minor)"
            best_mode_scale = aeolian
            best_non_dom_cov = non_dom_cov_aeolian
            best_full_cov = _coverage(all_pcs, aeolian)

    # "Common key + borrowed chords" correction (Approach A2):
    # Coverage-based ranking sometimes picks an exotic mode (Lydian, Mixolydian,
    # Dorian-as-parent, etc.) only because that mode happens to contain a chromatic
    # note from a single borrowed chord. A working musician reads the same progression
    # as the parallel common mode (Ionian/Aeolian) plus a borrowing — which is also
    # the more useful labeling for soloing and Roman numeral analysis.
    #
    # Discriminator: the kind of chord that uses the distinctive pitch.
    #   - dominant-7 chord uses it → transient borrowing (V/V, V/iv, etc.)
    #   - stable triad / maj7 / min7 / etc. uses it → structural mode feature
    # Real Dorian has IV major (stable). Real Lydian has II major (stable).
    # A V/V borrowing in a major key has D7 (dominant) — clearly different.
    EXOTIC_MAJOR_MODES = ("Lydian", "Mixolydian", "Phrygian Dominant")
    EXOTIC_MINOR_MODES = ("Dorian", "Phrygian", "Locrian")
    is_exotic = best_mode_name in (EXOTIC_MAJOR_MODES + EXOTIC_MINOR_MODES)
    if is_exotic:
        common_name = (
            "Ionian (Major)" if tonic_quality == "major"
            else "Aeolian (Natural Minor)"
        )
        common_scale = Scale.create(tonic_pc, common_name)
        common_full_cov = _coverage(all_pcs, common_scale)
        distinctive_pcs = best_mode_scale.pitch_class_set - common_scale.pitch_class_set
        DOMINANT_QUALITIES = ("7", "9", "11", "13", "7b5", "7#5", "7b9", "7#9", "aug7")
        structural_uses = sum(
            1 for c in progression.chords
            if (c.pitch_class_set & distinctive_pcs)
            and c.quality not in DOMINANT_QUALITIES
        )
        transient_uses = sum(
            1 for c in progression.chords
            if (c.pitch_class_set & distinctive_pcs)
            and c.quality in DOMINANT_QUALITIES
        )
        n_chords = len(progression.chords)
        distinctive_is_structural = structural_uses > 0
        distinctive_ratio = (structural_uses + transient_uses) / n_chords if n_chords else 0.0
        common_pcs = common_scale.pitch_class_set
        chromatic_pcs_in_progression = all_pcs - common_pcs
        multiple_chromatic_borrowings = len(chromatic_pcs_in_progression) >= 2

        is_borrowing_via_dominant = (
            common_full_cov >= 0.80
            and not distinctive_is_structural
            and distinctive_ratio < 0.5
        )
        is_borrowing_via_mixture = (
            common_full_cov >= 0.65
            and multiple_chromatic_borrowings
        )
        if is_borrowing_via_dominant or is_borrowing_via_mixture:
            best_mode_name = common_name
            best_mode_scale = common_scale
            best_non_dom_cov = _coverage(non_dom_pcs, common_scale) if non_dom_pcs else 1.0
            best_full_cov = common_full_cov

    parent_scales = [best_mode_scale]
    scale_system = "pure"
    notes: list[str] = []

    if dominant_chords and best_full_cov < 1.0:
        if tonic_quality == "minor":
            hm_scale = Scale.create(tonic_pc, "Harmonic Minor")
            v_chord_pcs: frozenset[int] = frozenset()
            for c in dominant_chords:
                v_chord_pcs = v_chord_pcs | c.pitch_class_set
            if v_chord_pcs.issubset(hm_scale.pitch_class_set):
                scale_system = "harmonic_minor_V"
                parent_scales = [best_mode_scale, hm_scale]
                notes.append(
                    f"V7 chord borrows from {tonic_name} harmonic minor "
                    f"(raised 7th: {note_name((tonic_pc + 11) % 12)})"
                )
        else:
            notes.append("Progression uses chromatic notes outside the parent scale")
    
    # Compute confidence
    if scale_system == "pure" and best_full_cov == 1.0:
        confidence = 1.0
    elif scale_system == "harmonic_minor_V":
        confidence = 0.95  # very high — recognized pattern
    else:
        confidence = best_full_cov * 0.8  # reduced when chromatic
    
    # Build display string
    mode_label = MODE_LABELS.get(best_mode_name, best_mode_name)
    if scale_system == "harmonic_minor_V":
        display = f"{tonic_name} {mode_label} (harmonic minor V)"
    elif scale_system == "pure" and best_full_cov == 1.0:
        display = f"{tonic_name} {mode_label}"
    elif best_full_cov >= 0.85:
        display = f"{tonic_name} {mode_label} (with chromatic notes)"
    else:
        display = f"{tonic_name} {mode_label} — chromatic/modulating"
        scale_system = "chromatic"
    
    return KeyAnalysis(
        tonic_pc=tonic_pc,
        tonic_name=tonic_name,
        mode_name=best_mode_name,
        mode_label=mode_label,
        scale_system=scale_system,
        parent_scales=parent_scales,
        confidence=confidence,
        display=display,
        notes=notes,
    )