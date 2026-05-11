"""
Multi-key modulation detection for chord progressions.

Where key_analyzer.analyze_key() answers "what single key fits this whole progression?",
this module answers "where does the progression's key CHANGE, and what's the key on
each side of the boundary?"

Approach: sliding window + re-analyze.

  1. Slide a 3-chord window across the progression. For each window position, call
     analyze_key() on that slice and record the (tonic_pc, mode_name) as a label.
  2. For each chord, take a vote across all windows containing it. Most common label
     wins; ties broken by continuity (match previous chord's assignment).
  3. Group consecutive same-label chords into sections. Absorb sections shorter
     than MIN_SECTION_LEN into neighbors (kills window-noise false modulations).
  4. For each final section's chord range, RE-RUN analyze_key() to get its full
     labeling (scale_system, confidence, display string). This is why section-level
     correctness inherits everything analyze_key() already does well — A2 logic,
     HM-V handling, blues detection, modal protection clauses, all of it.

The window/min-section knobs are the only tuning parameters. analyze_key() does
all the actual key identification.
"""

from __future__ import annotations
from collections import Counter
from typing import Optional
from .music_theory import ChordProgression
from .scales import Scale
from .key_analyzer import KeyAnalysis, KeySection, analyze_key


WINDOW_SIZE = 3
MIN_SECTION_LEN = 3

# Relative-key tiebreaker (catches Am↔C, Em↔G modulations that share pitch
# class sets). After window-based section detection, sections >= MIN_SPLIT_LEN
# chords are checked: is there a split point where both halves analyze to
# DIFFERENT tonics with combined confidence MIN_CONFIDENCE_DELTA higher than
# the un-split section? If yes, split.
#
# Threshold tuning:
#   0.00 = Y1 (aggressive, splits on any improvement)
#   0.15 = Y2 (conservative, requires notable improvement)
MIN_SPLIT_LEN = 6
MIN_CONFIDENCE_DELTA = 0.0


# ── Internal types ────────────────────────────────────────────────
# A "label" is a (tonic_pc, mode_name) tuple — the identifying pair for a key.
# We deliberately don't carry scale_system or confidence here; those are
# recomputed per-section at the end via analyze_key() on the section's slice.
Label = tuple[int, str]


def _label_from_analysis(analysis: Optional[KeyAnalysis]) -> Optional[Label]:
    """Extract the (tonic_pc, mode_name) label from a KeyAnalysis result."""
    if analysis is None:
        return None
    return (analysis.tonic_pc, analysis.mode_name)


def _slice_progression(progression: ChordProgression, start: int, end: int) -> ChordProgression:
    """Return a new ChordProgression containing chords[start:end] (end exclusive)."""
    return ChordProgression(
        chords=list(progression.chords[start:end]),
        name=progression.name,
    )


# ── Step 1: window labels ─────────────────────────────────────────

def _window_labels(progression: ChordProgression) -> list[Optional[Label]]:
    """For each window position i (start of a WINDOW_SIZE slice), return the
    label of analyze_key() on chords[i:i+WINDOW_SIZE].

    Returns a list of length (n_chords - WINDOW_SIZE + 1). For progressions
    shorter than WINDOW_SIZE, returns a single label covering the whole thing.
    """
    n = len(progression.chords)
    if n <= WINDOW_SIZE:
        return [_label_from_analysis(analyze_key(progression))]

    labels: list[Optional[Label]] = []
    for i in range(n - WINDOW_SIZE + 1):
        window = _slice_progression(progression, i, i + WINDOW_SIZE)
        labels.append(_label_from_analysis(analyze_key(window)))
    return labels


# ── Step 2: per-chord assignment via voting ───────────────────────

def _per_chord_labels(progression: ChordProgression,
                      window_labels: list[Optional[Label]]) -> list[Optional[Label]]:
    """Assign each chord a single label by voting across the windows that
    contain it. Ties broken by continuity with the previous chord's label.
    """
    n = len(progression.chords)
    if n <= WINDOW_SIZE:
        # One label covers everything
        single = window_labels[0] if window_labels else None
        return [single] * n

    assignments: list[Optional[Label]] = []
    for chord_idx in range(n):
        # Which windows contain this chord?
        # Window w covers chords [w, w + WINDOW_SIZE)
        # So chord c is in windows max(0, c - WINDOW_SIZE + 1) through min(n_windows-1, c)
        n_windows = len(window_labels)
        first_window = max(0, chord_idx - WINDOW_SIZE + 1)
        last_window = min(n_windows - 1, chord_idx)

        # Collect non-None labels from those windows
        candidates: list[Label] = []
        for w in range(first_window, last_window + 1):
            label = window_labels[w]
            if label is not None:
                candidates.append(label)

        if not candidates:
            assignments.append(None)
            continue

        # Vote
        counter = Counter(candidates)
        most_common = counter.most_common()
        top_count = most_common[0][1]
        tied = [label for label, count in most_common if count == top_count]

        if len(tied) == 1:
            assignments.append(tied[0])
        else:
            # Tie-break: prefer continuity with previous assignment if it's tied
            prev = assignments[-1] if assignments else None
            if prev is not None and prev in tied:
                assignments.append(prev)
            else:
                # Otherwise just take the first (deterministic)
                assignments.append(tied[0])

    return assignments


# ── Step 3: section consolidation + min-length filter ─────────────

def _group_consecutive(labels: list[Optional[Label]]) -> list[tuple[int, int, Optional[Label]]]:
    """Group consecutive same-label runs. Returns list of (start, end_inclusive, label)."""
    if not labels:
        return []
    runs: list[tuple[int, int, Optional[Label]]] = []
    current_label = labels[0]
    run_start = 0
    for i in range(1, len(labels)):
        if labels[i] != current_label:
            runs.append((run_start, i - 1, current_label))
            current_label = labels[i]
            run_start = i
    runs.append((run_start, len(labels) - 1, current_label))
    return runs


def _absorb_short_sections(
    runs: list[tuple[int, int, Optional[Label]]],
) -> list[tuple[int, int, Optional[Label]]]:
    """Merge sections shorter than MIN_SECTION_LEN into a neighbor.

    Strategy: repeatedly find the shortest section that's below threshold,
    merge it into whichever neighbor has the larger pitch-class-set overlap
    (or the longer neighbor if pcs don't help). Continue until all surviving
    sections meet the minimum, OR only one section remains.
    """
    if len(runs) <= 1:
        return list(runs)

    work = list(runs)
    while True:
        # Find shortest under-threshold section
        below: list[tuple[int, int]] = []  # (length, index_in_work)
        for idx, (start, end, _) in enumerate(work):
            length = end - start + 1
            if length < MIN_SECTION_LEN:
                below.append((length, idx))
        if not below:
            break
        if len(work) <= 1:
            break
        below.sort()
        target_idx = below[0][1]
        target = work[target_idx]
        target_label = target[2]

        # Choose neighbor to merge into
        left = work[target_idx - 1] if target_idx > 0 else None
        right = work[target_idx + 1] if target_idx < len(work) - 1 else None

        def overlap(neighbor_label: Optional[Label]) -> int:
            if neighbor_label is None or target_label is None:
                return -1
            n_pcs = Scale.create(neighbor_label[0], neighbor_label[1]).pitch_class_set
            t_pcs = Scale.create(target_label[0], target_label[1]).pitch_class_set
            return len(n_pcs & t_pcs)

        def neighbor_length(neighbor: Optional[tuple[int, int, Optional[Label]]]) -> int:
            if neighbor is None:
                return -1
            return neighbor[1] - neighbor[0] + 1

        if left is None and right is None:
            break  # nothing to merge into; pathological
        if left is None:
            merge_into = "right"
        elif right is None:
            merge_into = "left"
        else:
            left_ov = overlap(left[2])
            right_ov = overlap(right[2])
            if left_ov > right_ov:
                merge_into = "left"
            elif right_ov > left_ov:
                merge_into = "right"
            else:
                # Tie on overlap — prefer the longer neighbor
                merge_into = "left" if neighbor_length(left) >= neighbor_length(right) else "right"

        if merge_into == "left":
            assert left is not None
            new_run = (left[0], target[1], left[2])
            work = work[:target_idx - 1] + [new_run] + work[target_idx + 1:]
        else:
            assert right is not None
            new_run = (target[0], right[1], right[2])
            work = work[:target_idx] + [new_run] + work[target_idx + 2:]

    return work

def _merge_vamp_sections(
    progression: ChordProgression,
    runs: list[tuple[int, int, Optional[Label]]],
) -> list[tuple[int, int, Optional[Label]]]:
    """Merge adjacent sections whose chord sets overlap heavily.

    If two consecutive sections share more than half their unique chords,
    they're a vamp (repeating pattern), not a real modulation. The window-
    labeling may have assigned them different tonics because each window
    individually fits both relative interpretations equally well — but
    that's the analyzer being confused by a vamp, not a real key change.

    Re-runs until no adjacent sections can be merged.
    """
    def chord_id(c):
        return (c.root, c.quality)

    work = list(runs)
    while len(work) >= 2:
        merged_any = False
        i = 0
        while i < len(work) - 1:
            left_start, left_end, left_label = work[i]
            right_start, right_end, right_label = work[i + 1]
            left_ids = {chord_id(c) for c in progression.chords[left_start:left_end + 1]}
            right_ids = {chord_id(c) for c in progression.chords[right_start:right_end + 1]}
            if not left_ids or not right_ids:
                i += 1
                continue
            overlap = len(left_ids & right_ids) / min(len(left_ids), len(right_ids))
            if overlap > 0.5:
                # Merge: take the longer section's label
                left_len = left_end - left_start + 1
                right_len = right_end - right_start + 1
                keep_label = left_label if left_len >= right_len else right_label
                work = (
                    work[:i]
                    + [(left_start, right_end, keep_label)]
                    + work[i + 2:]
                )
                merged_any = True
                break  # restart scan after merge
            i += 1
        if not merged_any:
            break
    return work


# ── Step 4: re-analyze each final section ─────────────────────────

def _build_section(progression: ChordProgression,
                   start: int, end: int) -> Optional[KeySection]:
    """Run analyze_key() on chords[start:end+1] and wrap the result as a KeySection."""
    section_prog = _slice_progression(progression, start, end + 1)
    analysis = analyze_key(section_prog)
    if analysis is None:
        return None
    return KeySection(
        start_index=start,
        end_index=end,
        tonic_pc=analysis.tonic_pc,
        tonic_name=analysis.tonic_name,
        mode_name=analysis.mode_name,
        mode_label=analysis.mode_label,
        scale_system=analysis.scale_system,
        confidence=analysis.confidence,
    )

# ── Relative-key tiebreaker ───────────────────────────────────────

def _try_relative_split(progression: ChordProgression,
                        start: int, end: int) -> Optional[tuple[int, int, int]]:
    """Check if a section that analyze_key() merged into one key actually
    contains a relative-key modulation (Am→C, Em→G, etc.).

    Returns (split_index, ignored, ignored) where split_index is the FIRST
    chord index of the second half, or None if no good split found.
    The split_index is relative to the full progression, not the section.
    """
    section_len = end - start + 1
    if section_len < MIN_SPLIT_LEN:
        return None

    # Baseline: confidence of the un-split section
    baseline = analyze_key(_slice_progression(progression, start, end + 1))
    if baseline is None:
        return None
    baseline_conf = baseline.confidence
    baseline_tonic = baseline.tonic_pc

    # Try every interior split point. Each half needs at least 3 chords to be
    # analyzed reliably (matches WINDOW_SIZE).
    best_split: Optional[int] = None
    best_score = baseline_conf + MIN_CONFIDENCE_DELTA  # must beat this

    # Pre-compute chord identity per chord in the section (root + quality)
    def chord_id(c):
        return (c.root, c.quality)
    chord_ids = [chord_id(c) for c in progression.chords[start:end + 1]]

    for split in range(start + 3, end - 1):  # split is index of first chord of right half
        left = analyze_key(_slice_progression(progression, start, split))
        right = analyze_key(_slice_progression(progression, split, end + 1))
        if left is None or right is None:
            continue
        # Must produce different tonics — otherwise it's not a split
        if left.tonic_pc == right.tonic_pc and left.mode_name == right.mode_name:
            continue
        # At least one half must have a tonic different from baseline
        if left.tonic_pc == baseline_tonic and right.tonic_pc == baseline_tonic:
            continue
        # Structural guard: don't split a vamp. If the two halves share more
        # than half their unique chords, this is a repeating pattern, not a
        # modulation — the analyzer is just finding the relative tonic on
        # the second iteration of the same chords.
        left_offset = split - start
        left_ids = set(chord_ids[:left_offset])
        right_ids = set(chord_ids[left_offset:])
        if left_ids and right_ids:
            overlap_ratio = len(left_ids & right_ids) / min(len(left_ids), len(right_ids))
            if overlap_ratio > 0.5:
                continue
        avg_conf = (left.confidence + right.confidence) / 2
        if avg_conf > best_score:
            best_score = avg_conf
            best_split = split

    if best_split is None:
        return None
    return (best_split, 0, 0)  # tuple shape for caller convenience


def _apply_relative_splits(
    progression: ChordProgression,
    runs: list[tuple[int, int, Optional[Label]]],
) -> list[tuple[int, int, Optional[Label]]]:
    """For each section, check if it should be split via relative-key tiebreaker.
    Returns a new runs list with any splits applied. The labels on split sections
    are set to None — they get recomputed by analyze_key() in step 4."""
    result: list[tuple[int, int, Optional[Label]]] = []
    for run_start, run_end, label in runs:
        split_info = _try_relative_split(progression, run_start, run_end)
        if split_info is None:
            result.append((run_start, run_end, label))
        else:
            split_idx = split_info[0]
            result.append((run_start, split_idx - 1, None))
            result.append((split_idx, run_end, None))
    return result

# ── Public API ────────────────────────────────────────────────────

def analyze_key_sections(progression: ChordProgression) -> Optional[KeyAnalysis]:
    """Multi-key analysis of a chord progression.

    Returns a KeyAnalysis whose .sections field contains one KeySection per
    contiguous run of the same key. For non-modulating progressions, .sections
    has a single element. The top-level fields (.tonic_pc, .mode_name, etc.)
    reflect the LONGEST section.

    Returns None if the progression is empty.
    """
    if not progression.chords:
        return None

    # Steps 1-2: per-chord labels via windowed analyze_key()
    win_labels = _window_labels(progression)
    chord_labels = _per_chord_labels(progression, win_labels)

    # Step 3: group + absorb short sections
    runs = _group_consecutive(chord_labels)
    runs = _absorb_short_sections(runs)

    # Step 3.4: merge adjacent vamp sections that got falsely split by windowing
    runs = _merge_vamp_sections(progression, runs)

    # Step 3.5: relative-key tiebreaker (catches Am↔C, Em↔G modulations
    # that share pitch class sets and so are invisible to window labeling)
    runs = _apply_relative_splits(progression, runs)


    # Step 4: re-analyze each surviving section for proper labeling
    sections: list[KeySection] = []
    for start, end, _ in runs:
        section = _build_section(progression, start, end)
        if section is not None:
            sections.append(section)

    if not sections:
        # Fallback: analyze the whole thing as one section
        whole = analyze_key(progression)
        if whole is None:
            return None
        sections = [KeySection(
            start_index=0,
            end_index=len(progression.chords) - 1,
            tonic_pc=whole.tonic_pc,
            tonic_name=whole.tonic_name,
            mode_name=whole.mode_name,
            mode_label=whole.mode_label,
            scale_system=whole.scale_system,
            confidence=whole.confidence,
        )]

    # Primary section = longest by chord count
    primary = max(sections, key=lambda s: s.end_index - s.start_index + 1)

    # Display string
    if len(sections) == 1:
        s = sections[0]
        # Reuse the display format conventions from analyze_key()
        whole = analyze_key(progression)
        display = whole.display if whole is not None else f"{s.tonic_name} {s.mode_label}"
    else:
        section_strs = [f"{s.tonic_name} {s.mode_label}" for s in sections]
        display = f"modulating: {' → '.join(section_strs)}"

    # Overall confidence: chord-weighted average of section confidences
    total_chords = sum(s.end_index - s.start_index + 1 for s in sections)
    confidence = sum(
        s.confidence * (s.end_index - s.start_index + 1) / total_chords
        for s in sections
    ) if total_chords else 0.0

    parent_scales = [Scale.create(s.tonic_pc, s.mode_name) for s in sections]
    notes: list[str] = []
    if len(sections) > 1:
        notes.append(
            f"Detected {len(sections)} key sections: "
            + ", ".join(
                f"bars {s.start_index + 1}-{s.end_index + 1} in {s.tonic_name} {s.mode_label}"
                for s in sections
            )
        )

    return KeyAnalysis(
        tonic_pc=primary.tonic_pc,
        tonic_name=primary.tonic_name,
        mode_name=primary.mode_name,
        mode_label=primary.mode_label,
        scale_system=primary.scale_system,
        parent_scales=parent_scales,
        confidence=confidence,
        display=display,
        notes=notes,
        sections=sections,
    )