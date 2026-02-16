"""
Scale matching engine.
Given a chord progression, find the best-fitting scales ranked by
coverage (all chord tones present) and economy (fewest extraneous notes).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .music_theory import ChordProgression, Chord, note_name
from .scales import Scale, SCALE_CATALOG


@dataclass
class ScaleMatch:
    """Result of matching a scale against a chord progression."""
    scale: Scale
    coverage: float       # 0.0–1.0: fraction of chord tones covered by scale
    economy: float        # 0.0–1.0: 1 - (extra notes / scale size)
    missing_notes: frozenset[int]   # chord tones NOT in the scale
    extra_notes: frozenset[int]     # scale tones NOT in chord tones
    score: float          # combined ranking score

    @property
    def is_perfect(self) -> bool:
        """True if the scale contains ALL chord tones."""
        return self.coverage == 1.0

    @property
    def display_name(self) -> str:
        return self.scale.display_name

    def missing_note_names(self) -> list[str]:
        return [note_name(pc) for pc in sorted(self.missing_notes)]

    def extra_note_names(self) -> list[str]:
        return [note_name(pc) for pc in sorted(self.extra_notes)]


def match_scale(progression: ChordProgression, scale: Scale,
                coverage_weight: float = 0.7,
                economy_weight: float = 0.3) -> ScaleMatch:
    """
    Score a single scale against a chord progression.

    Coverage: What fraction of the progression's pitch classes are in the scale?
    Economy: How tight is the fit? (Fewer extra notes = better)

    Weights default to 70/30 favoring coverage — missing a chord tone is
    worse than having an extra passing tone.
    """
    chord_pcs = progression.all_pitch_classes
    scale_pcs = scale.pitch_class_set

    if not chord_pcs:
        return ScaleMatch(scale=scale, coverage=0.0, economy=0.0,
                          missing_notes=frozenset(), extra_notes=frozenset(), score=0.0)

    covered = chord_pcs & scale_pcs
    missing = chord_pcs - scale_pcs
    extra = scale_pcs - chord_pcs

    coverage = len(covered) / len(chord_pcs) if chord_pcs else 0.0
    economy = 1.0 - (len(extra) / len(scale_pcs)) if scale_pcs else 0.0

    score = (coverage * coverage_weight) + (economy * economy_weight)

    return ScaleMatch(
        scale=scale,
        coverage=coverage,
        economy=economy,
        missing_notes=frozenset(missing),
        extra_notes=frozenset(extra),
        score=score,
    )


def find_matching_scales(
    progression: ChordProgression,
    top_n: int = 10,
    require_perfect_coverage: bool = False,
    exclude_chromatic: bool = True,
    scale_filter: Optional[list[str]] = None,
    coverage_weight: float = 0.7,
    economy_weight: float = 0.3,
) -> list[ScaleMatch]:
    """
    Find the best-fitting scales for a chord progression.

    Args:
        progression: The chord progression to match against.
        top_n: Number of top results to return.
        require_perfect_coverage: If True, only return scales that cover ALL chord tones.
        exclude_chromatic: Skip chromatic scale (it always matches everything).
        scale_filter: Optional list of scale names to limit search to.
        coverage_weight: Weight for coverage in scoring (0-1).
        economy_weight: Weight for economy in scoring (0-1).

    Returns:
        List of ScaleMatch objects, sorted by score descending.
    """
    results: list[ScaleMatch] = []

    scale_names = scale_filter if scale_filter else list(SCALE_CATALOG.keys())

    for scale_name in scale_names:
        if exclude_chromatic and scale_name == "Chromatic":
            continue

        # Try every root
        for root in range(12):
            scale = Scale.create(root, scale_name)
            m = match_scale(progression, scale, coverage_weight, economy_weight)

            if require_perfect_coverage and not m.is_perfect:
                continue

            results.append(m)

    # Sort: score desc, then coverage desc, then economy desc
    results.sort(key=lambda m: (m.score, m.coverage, m.economy), reverse=True)

    # Deduplicate: same pitch class set can appear under different names
    seen: set[tuple[str, frozenset[int]]] = set()
    unique: list[ScaleMatch] = []
    for m in results:
        key = (m.scale.name, m.scale.pitch_class_set)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique[:top_n]


def suggest_scales(
    progression: ChordProgression,
    top_n: int = 3,
    alternatives: int = 5,
) -> dict[str, list[ScaleMatch]]:
    """
    High-level suggestion function.

    Returns:
        {
            "top": [top_n best matches with perfect or near-perfect coverage],
            "alternatives": [next best alternatives],
        }
    """
    # First pass: perfect coverage only
    perfect = find_matching_scales(progression, top_n=top_n + alternatives,
                                   require_perfect_coverage=True)

    if len(perfect) >= top_n:
        return {
            "top": perfect[:top_n],
            "alternatives": perfect[top_n:top_n + alternatives],
        }

    # If not enough perfect matches, also include near-perfect
    all_matches = find_matching_scales(progression, top_n=top_n + alternatives,
                                       require_perfect_coverage=False)

    return {
        "top": all_matches[:top_n],
        "alternatives": all_matches[top_n:top_n + alternatives],
    }


def analyze_chord_in_scale(chord: Chord, scale: Scale) -> dict:
    """
    Analyze how a single chord fits within a scale.
    Returns degree information and whether it's diatonic.
    """
    root_degree = scale.degree_of(chord.root)
    chord_pcs = chord.pitch_class_set
    scale_pcs = scale.pitch_class_set
    is_diatonic = chord_pcs.issubset(scale_pcs)
    covered = chord_pcs & scale_pcs
    missing = chord_pcs - scale_pcs

    return {
        "chord": chord.display_name,
        "root_degree": root_degree,  # None if root not in scale
        "is_diatonic": is_diatonic,
        "covered_tones": len(covered),
        "total_tones": len(chord_pcs),
        "missing_notes": [note_name(pc) for pc in sorted(missing)],
    }
