"""Core music theory and audio engine package."""

from .music_theory import (
    Chord, ChordProgression, note_name, parse_note,
    SHARP_NAMES, FLAT_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY,
)
from .scales import (
    Scale, SCALE_CATALOG, SCALE_CATEGORIES,
    build_scale, get_all_scale_names, get_all_categories,
)
from .scale_matcher import suggest_scales, find_matching_scales, ScaleMatch
from .tuning import Tuning, get_all_tuning_presets
from .audio_engine import AudioEngine, GM_PROGRAMS
from .backing_tracks import BackingTrackEngine
