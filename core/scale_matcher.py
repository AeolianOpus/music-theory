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

    # Prefer 7-note scales; slightly penalize larger scales
    size_penalty = max(0, len(scale_pcs) - 7) * 0.02
    score = (coverage * coverage_weight) + (economy * economy_weight) - size_penalty

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
    
def detect_key(progression: ChordProgression, min_coverage: float = 1.0) -> dict:
    """
    Find all keys and improv scales that can contain the progression's pitch classes.
    
    Args:
        progression: The chord progression to analyze.
        min_coverage: Minimum fraction of chord tones that must fit (1.0 = perfect).
    
    Returns:
        A dict with two lists:
            - "keys": 7-note diatonic and modal scales (tonal centers)
            - "improv": 5-6 note pentatonic and blues scales (for soloing)
        Each list contains dicts with "scale", "display", and "coverage".
        Returns {"keys": [], "improv": []} if progression is empty.
    """
    empty_result = {"keys": [], "improv": []}
    
    if not progression.chords:
        return empty_result
    
    chord_pcs = progression.all_pitch_classes
    if not chord_pcs:
        return empty_result
    
    # 7-note scales — used as keys / tonal centers
    key_scales = (
        "Ionian (Major)",
        "Aeolian (Natural Minor)",
        "Harmonic Minor",
        "Melodic Minor",
        "Dorian",
        "Phrygian",
        "Lydian",
        "Mixolydian",
        "Locrian",
        "Phrygian Dominant",
        "Lydian Dominant",
        "Hungarian Minor",
        "Double Harmonic Major",
    )
    
    # 5-6 note scales — used for improvisation over a key
    improv_scales = (
        "Minor Pentatonic",
        "Major Pentatonic",
        "Blues",
        "Major Blues",
    )
    
    # Display labels
    quality_labels = {
        "Ionian (Major)": "major",
        "Aeolian (Natural Minor)": "minor",
        "Harmonic Minor": "harmonic minor",
        "Melodic Minor": "melodic minor",
        "Dorian": "Dorian",
        "Phrygian": "Phrygian",
        "Lydian": "Lydian",
        "Mixolydian": "Mixolydian",
        "Locrian": "Locrian",
        "Phrygian Dominant": "Phrygian Dominant",
        "Lydian Dominant": "Lydian Dominant",
        "Hungarian Minor": "Hungarian minor",
        "Double Harmonic Major": "Double Harmonic major",
        "Minor Pentatonic": "minor pentatonic",
        "Major Pentatonic": "major pentatonic",
        "Blues": "blues",
        "Major Blues": "major blues",
    }
    
    def _scan(scale_names: tuple) -> list[dict]:
        results: list[dict] = []
        for root in range(12):
            for scale_name in scale_names:
                scale = Scale.create(root, scale_name)
                covered = chord_pcs & scale.pitch_class_set
                coverage = len(covered) / len(chord_pcs)
                
                if coverage < min_coverage:
                    continue
                
                quality = quality_labels.get(scale_name, scale_name)
                display = f"{note_name(root)} {quality}"
                
                results.append({
                    "scale": scale,
                    "display": display,
                    "coverage": coverage,
                })
        
        # Sort purely by coverage (no commonness bias)
        results.sort(key=lambda m: -m["coverage"])
        return results
    
    return {
        "keys": _scan(key_scales),
        "improv": _scan(improv_scales),
    }