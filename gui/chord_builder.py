from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QVBoxLayout, QGroupBox, QListView, QAbstractItemView, QTabWidget,
    QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize, QSettings, QStandardPaths
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
import json
from typing import Optional
import os
from datetime import datetime

from core.audio_engine import AudioEngine, PIANO_CHANNEL
from core.playback import PlaybackEngine, STYLE_PRESETS
from core.dawdreamer_engine import DawDreamerEngine
from core.music_theory import QUALITY_FULL_NAMES, Chord, ChordProgression, SHARP_NAMES, GUITAR_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY, QUALITY_FULL_NAMES, note_name
from core.scale_matcher import suggest_scales, detect_key, match_scale
from core.key_analyzer import analyze_key
from core.modulation_detector import analyze_key_sections
from core.roman_analyzer import analyze_roman
from core.chord_scale_coach import analyze_chord_scales
from gui.saved_library import register_save

# Chord quality categories for button layout
QUALITY_CATEGORIES = {
    "Triads": ["maj", "min", "dim", "aug"],
    "7ths": ["maj7", "min7", "7", "dim7", "m7b5", "minmaj7", "aug7", "augmaj7"],
    "Extended": ["9", "maj9", "min9", "11", "min11", "13", "min13"],
    "Altered": ["7b5", "7#5", "7b9", "7#9", "add9", "madd9"],
    "Sus & Other": ["sus2", "sus4", "6", "min6", "5"],
}

# Rhythm patterns for progression playback
# Each pattern is a list of relative durations (will be scaled by chord_duration)
RHYTHM_PATTERNS = {
    "Straight": [1.0],  # All chords same duration
    "Waltz (3/4)": [1.5, 0.75, 0.75],  # Long-short-short
    "Shuffle": [1.33, 0.67],  # Long-short swing feel
    "Blues (12-bar feel)": [2.0, 2.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],  # Typical blues timing
}


# ── Per-chord display helpers (used by Per Chord tab) ────────────────

# Priority marker glyphs. Per Constantine's spec:
#   priority 0 (primary)   → ◇ diamond
#   priority 1 (secondary) → ● filled circle
#   priority 2 (color/outside) → ○ open circle
PRIORITY_MARKERS = {0: "◇", 1: "●", 2: "○"}

# Idiom tag colors. Each idiom gets a distinct Catppuccin Mocha color
# so the user can scan a chord section and identify the style of each
# scale suggestion at a glance.
IDIOM_COLORS = {
    "universal":    "#6c7086",  # muted gray — works in any context
    "rock_blues":   "#f38ba8",  # red — energy
    "jazz":         "#cba6f7",  # purple — sophistication
    "neoclassical": "#f9e2af",  # gold — Yngwie territory
    "fusion":       "#94e2d5",  # teal — modern hybrid
}

# How many options to show in each chord section before the
# "+ N more suggestions" link collapses the rest.
DEFAULT_OPTIONS_VISIBLE = 3

# All available idiom tags, in the order they appear in the filter row.
ALL_IDIOMS = ["universal", "rock_blues", "jazz", "neoclassical", "fusion"]


def _format_scale_notes(scale) -> str:
    """Render a scale's notes as a space-separated string.
    e.g., 'A B C D E F G#' for A harmonic minor."""
    from core.music_theory import note_name
    return " ".join(note_name(pc) for pc in scale.pitch_classes)


def _format_scale_formula(scale) -> str:
    """Render a scale's interval formula as scale degrees.
    e.g., '1 2 b3 4 5 b6 7' for harmonic minor.

    Reads scale.intervals (semitones from root) and maps each to its
    degree label, using major scale as the reference (1 2 3 4 5 6 7 = 0 2 4 5 7 9 11)."""
    # Degree labels indexed by semitone distance from root.
    # Returns the most common name for each interval.
    semitone_to_degree = {
        0:  "1",
        1:  "b2",
        2:  "2",
        3:  "b3",
        4:  "3",
        5:  "4",
        6:  "b5",
        7:  "5",
        8:  "b6",
        9:  "6",
        10: "b7",
        11: "7",
    }
    parts = []
    for semi in scale.intervals:
        # Wrap into 0-11 for any extended intervals (9ths, 11ths, etc.)
        # Compound intervals like the 9th (14 semitones) display as "9"
        # rather than "2" — handle that explicitly.
        compound = {
            13: "b9", 14: "9", 15: "#9",
            17: "11", 18: "#11",
            20: "b13", 21: "13",
        }
        if semi in compound:
            parts.append(compound[semi])
        else:
            parts.append(semitone_to_degree.get(semi % 12, "?"))
    return " ".join(parts)


def _format_chord_coverage(scale, chord) -> str:
    """Render how the scale's notes relate to the chord's notes.

    Returns a human-readable string like:
        "Covers all 3 chord tones: A (1), C (b3), E (5)"
    or, if some chord tones are missing from the scale:
        "Covers 2 of 3 chord tones: A (1), E (5). Missing: C"

    The chord-tone pitch classes are checked for membership in the
    scale's pitch class set; degree labels are computed relative to the
    chord root, not the scale root."""
    from core.music_theory import note_name

    scale_pcs = set(scale.pitch_classes)
    chord_pcs = list(chord.pitch_class_set)  # ordered by interval from root

    semitone_to_degree = {
        0: "1", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
        6: "b5", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7",
    }

    covered_parts: list[str] = []
    missing_parts: list[str] = []
    for chord_pc in chord_pcs:
        interval_from_root = (chord_pc - chord.root) % 12
        degree = semitone_to_degree.get(interval_from_root, "?")
        label = f"{note_name(chord_pc)} ({degree})"
        if chord_pc in scale_pcs:
            covered_parts.append(label)
        else:
            missing_parts.append(note_name(chord_pc))

    total = len(chord_pcs)
    covered = len(covered_parts)

    if covered == total:
        return f"Covers all {total} chord tones: {', '.join(covered_parts)}"
    if covered == 0:
        return f"No chord tones covered (chord tones: {', '.join(missing_parts)})"
    return (
        f"Covers {covered} of {total} chord tones: "
        f"{', '.join(covered_parts)}. Missing: {', '.join(missing_parts)}"
    )

class ChordChip(QWidget):
    """A single chord chip: name + × button, draggable via the parent list."""

    delete_requested = Signal(object)  # emits self
    right_clicked = Signal(int)        # emits chord index

    def __init__(self, chord_display: str, roman: str = "", parent=None):
        super().__init__(parent)
        self.chord_display = chord_display

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(4)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)

        self.label = QLabel(chord_display)
        self.label.setStyleSheet(
            "color: #cdd6f4; font-size: 14pt; font-weight: bold; background: transparent;"
        )
        text_col.addWidget(self.label)

        if roman:
            self.roman_label = QLabel(roman)
            self.roman_label.setStyleSheet(
                "color: #89b4fa; font-size: 9pt; font-style: italic; background: transparent;"
            )
            text_col.addWidget(self.roman_label)

        layout.addLayout(text_col)

        self.delete_btn = QPushButton("×")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                color: #a6adc8;
                background: transparent;
                border: none;
                font-size: 14pt;
                font-weight: bold;
                padding: 0;
            }
            QPushButton:hover {
                color: #f38ba8;
            }
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        layout.addWidget(self.delete_btn)

        self.setStyleSheet("""
            ChordChip {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
            ChordChip:hover {
                background-color: #45475a;
                border-color: #89b4fa;
            }
        """)
        self.chord_index: int = -1

    def contextMenuEvent(self, event) -> None:
        self.right_clicked.emit(self.chord_index)
        
class _IdiomPill(QLabel):
    """A single idiom tag rendered as a colored pill. Used inside
    _ScaleOptionRow to display one of the scale's idiom tags."""

    def __init__(self, idiom: str, parent: QWidget | None = None):
        super().__init__(idiom.replace("_", " "), parent)
        color = IDIOM_COLORS.get(idiom, "#6c7086")
        # Background uses the color at low alpha for fill, text uses
        # the full color for contrast.
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: rgba(180, 190, 254, 20);
                border: 1px solid {color};
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 9pt;
                font-weight: bold;
            }}
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class _ScaleOptionRow(QFrame):
    """A single scale suggestion within a chord section.

    Default view: priority marker + scale name + reason + idiom pills.
    Click anywhere on the row header to expand and reveal notes,
    formula, and chord-tone coverage for this scale against the chord."""

    def __init__(
        self,
        option,
        chord,
        parent: QWidget | None = None,
    ):
        """option: ChordScaleOption from core.chord_scale_coach
        chord:  the Chord this option is being suggested for
                (needed for chord-tone coverage)"""
        super().__init__(parent)
        self.option = option
        self.chord = chord
        self.expanded = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("""
            _ScaleOptionRow {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            _ScaleOptionRow:hover {
                background-color: rgba(180, 190, 254, 15);
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row (always visible) ──
        self._header_widget = QWidget()
        header = QHBoxLayout(self._header_widget)
        header.setContentsMargins(8, 4, 8, 4)
        header.setSpacing(8)

        # Priority marker
        marker_text = PRIORITY_MARKERS.get(option.priority, "·")
        marker_color = {
            0: "#f9e2af",  # gold — primary
            1: "#89b4fa",  # blue — secondary
            2: "#a6adc8",  # gray — color/outside
        }.get(option.priority, "#a6adc8")
        marker_label = QLabel(marker_text)
        marker_label.setStyleSheet(
            f"color: {marker_color}; font-size: 13pt; "
            "font-weight: bold; background: transparent;"
        )
        marker_label.setFixedWidth(20)
        marker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(marker_label)

        # Scale display name (bold)
        scale_label = QLabel(option.scale.display_name)
        scale_label.setStyleSheet(
            "color: #cdd6f4; font-size: 11pt; font-weight: bold; background: transparent;"
        )
        scale_label.setMinimumWidth(180)
        header.addWidget(scale_label)

        # Reason / explanation — muted, takes remaining space.
        # Strip the leading "<roman> — " prefix from reason since the
        # Roman numeral is already shown in the section header above.
        reason_text = option.reason
        for sep in (" — ", " - "):
            if sep in reason_text:
                _, _, rest = reason_text.partition(sep)
                if rest.strip():
                    reason_text = rest.strip()
                    break

        reason_label = QLabel(reason_text)
        reason_label.setStyleSheet(
            "color: #a6adc8; font-size: 10pt; background: transparent;"
        )
        reason_label.setWordWrap(True)
        reason_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        header.addWidget(reason_label, 1)

        # Idiom pills
        pills_widget = QWidget()
        pills_layout = QHBoxLayout(pills_widget)
        pills_layout.setContentsMargins(0, 0, 0, 0)
        pills_layout.setSpacing(4)
        for idiom in option.idioms:
            pill = _IdiomPill(idiom)
            pills_layout.addWidget(pill)
        header.addWidget(pills_widget)

        outer.addWidget(self._header_widget)

        # ── Details panel (hidden by default) ──
        self._details_widget = QWidget()
        details = QVBoxLayout(self._details_widget)
        details.setContentsMargins(36, 6, 16, 10)  # indented under the scale name
        details.setSpacing(4)

        notes_str = _format_scale_notes(option.scale)
        formula_str = _format_scale_formula(option.scale)
        coverage_str = _format_chord_coverage(option.scale, chord)

        for label_text, value_text in (
            ("Notes:",    notes_str),
            ("Formula:",  formula_str),
            ("Coverage:", coverage_str),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            key_lbl = QLabel(label_text)
            key_lbl.setStyleSheet(
                "color: #89b4fa; font-size: 10pt; font-weight: bold; "
                "background: transparent;"
            )
            key_lbl.setFixedWidth(70)
            row.addWidget(key_lbl)

            val_lbl = QLabel(value_text)
            val_lbl.setStyleSheet(
                "color: #cdd6f4; font-size: 10pt; background: transparent;"
            )
            val_lbl.setWordWrap(True)
            val_lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            row.addWidget(val_lbl, 1)
            details.addLayout(row)

        self._details_widget.setVisible(False)
        outer.addWidget(self._details_widget)

    def mousePressEvent(self, event) -> None:
        """Click anywhere on the row to toggle the details panel."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.expanded = not self.expanded
            self._details_widget.setVisible(self.expanded)
        super().mousePressEvent(event)


class _ChordAdviceSection(QFrame):
    """All scale advice for ONE chord in the progression.

    Header: chord display name (large) above Roman numeral (small subtitle).
    Body: a vertical stack of _ScaleOptionRow widgets — one per scale option.

    The chord_obj parameter is the underlying Chord object — needed by
    _ScaleOptionRow for chord-tone coverage calculation in the per-option
    info expander."""

    def __init__(
        self,
        chord_display: str,
        roman_numeral: str,
        options: list,
        chord_obj,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            _ChordAdviceSection {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # ── Header: chord name big, Roman numeral as subtitle ──
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        chord_label = QLabel(chord_display)
        chord_label.setStyleSheet(
            "color: #f5c2e7; font-size: 18pt; font-weight: bold; background: transparent;"
        )
        header_layout.addWidget(chord_label)

        roman_label = QLabel(roman_numeral)
        roman_label.setStyleSheet(
            "color: #89b4fa; font-size: 11pt; font-style: italic; background: transparent;"
        )
        header_layout.addWidget(roman_label)

        outer.addWidget(header_widget)

        # Thin divider between header and options
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #45475a; background-color: #45475a; max-height: 1px;")
        outer.addWidget(divider)

        # ── Scale options ──
        if not options:
            empty = QLabel("(no scale suggestions available)")
            empty.setStyleSheet(
                "color: #6c7086; font-style: italic; padding: 8px;"
            )
            outer.addWidget(empty)
        else:
            hidden_rows: list[_ScaleOptionRow] = []
            for idx, option in enumerate(options):
                row = _ScaleOptionRow(option, chord_obj)
                outer.addWidget(row)
                if idx >= DEFAULT_OPTIONS_VISIBLE:
                    row.setVisible(False)
                    hidden_rows.append(row)

            if hidden_rows:
                n = len(hidden_rows)
                more_link = QLabel(f"+ {n} more suggestion{'s' if n > 1 else ''}")
                more_link.setStyleSheet(
                    "color: #89b4fa; font-size: 10pt; padding: 4px 8px; "
                    "background: transparent;"
                )
                more_link.setCursor(Qt.CursorShape.PointingHandCursor)

                def toggle_hidden(lbl=more_link, rows=hidden_rows, count=n):
                    showing = rows[0].isVisible()
                    for r in rows:
                        r.setVisible(not showing)
                    lbl.setText(
                        f"− hide {count} suggestion{'s' if count > 1 else ''}"
                        if not showing
                        else f"+ {count} more suggestion{'s' if count > 1 else ''}"
                    )

                more_link.mousePressEvent = lambda e, fn=toggle_hidden: fn()
                outer.addWidget(more_link)

class ChordBuilder(QWidget):
    # Signal other widgets can listen to (fretboard, piano, etc.)
    progression_changed = Signal(object)   # emits ChordProgression
    scale_selected = Signal(object)        # emits ScaleMatch
    chord_tones_selected = Signal(object)  # emits Chord
    
    def __init__(
        self,
        audio_engine: AudioEngine | None = None,
        dawdreamer_engine: DawDreamerEngine | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.progression = ChordProgression()
        self.audio = audio_engine
        self.daw = dawdreamer_engine
        self.playback = (
            PlaybackEngine(audio_engine, dawdreamer_engine=dawdreamer_engine)
            if audio_engine
            else None
        )
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── Chord input row ──
        input_row = QHBoxLayout()

        # Root note buttons
        from PySide6.QtWidgets import QButtonGroup

        input_row.addWidget(QLabel("Root:"))
        self.root_group = QButtonGroup(self)
        self.root_buttons: list[QPushButton] = []
        for i, name in enumerate(GUITAR_NAMES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedWidth(48)
            self.root_group.addButton(btn, i)
            self.root_buttons.append(btn)
            input_row.addWidget(btn)
        self.root_buttons[0].setChecked(True)  # default to C

        input_row.addStretch()  # Add space between keys and controls

        # Add chord controls to this row
        self.add_btn = QPushButton("➕ Add Chord")
        self.add_btn.clicked.connect(self._add_chord)
        self.add_btn.setFixedHeight(50)
        self.add_btn.setMinimumWidth(120)
        input_row.addWidget(self.add_btn)

        self.clear_btn = QPushButton("🗑️ Clear All")
        self.clear_btn.clicked.connect(self._clear_progression)
        self.clear_btn.setFixedHeight(45)
        self.clear_btn.setMinimumWidth(90)
        input_row.addWidget(self.clear_btn)

        # Resize Add Chord to match Clear All / Play / Arpeggio / Stop sizing
        self.add_btn.setFixedHeight(45)
        self.add_btn.setMinimumWidth(100)

        input_row.addStretch()  # Separator before Save/Load group

        # Save + Load buttons
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self._save_progression)
        self.save_btn.setFixedHeight(45)
        self.save_btn.setMinimumWidth(90)
        input_row.addWidget(self.save_btn)

        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self._load_progression)
        self.load_btn.setFixedHeight(45)
        self.load_btn.setMinimumWidth(90)
        input_row.addWidget(self.load_btn)

        input_row.addStretch()  # Separator before playback controls

        # Play button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self._play_chord)
        self.play_btn.setFixedHeight(45)
        self.play_btn.setMinimumWidth(90)
        input_row.addWidget(self.play_btn)

        # Arpeggio button
        self.arp_btn = QPushButton("🎵 Arpeggio")
        self.arp_btn.clicked.connect(self._play_arpeggio)
        self.arp_btn.setFixedHeight(45)
        self.arp_btn.setMinimumWidth(100)
        input_row.addWidget(self.arp_btn)

        # Stop button
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setFixedHeight(45)
        self.stop_btn.setMinimumWidth(90)
        input_row.addWidget(self.stop_btn)

        layout.addLayout(input_row)  # Add the root buttons row
        
        # Quality category tabs (separate row)
        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("Quality:"))
        self.category_group = QButtonGroup(self)
        self.category_buttons: dict[str, QPushButton] = {}
        for i, category in enumerate(QUALITY_CATEGORIES.keys()):
            btn = QPushButton(category)
            btn.setCheckable(True)
            btn.setFixedWidth(100)
            self.category_group.addButton(btn, i)
            self.category_buttons[category] = btn
            category_row.addWidget(btn)
        
        category_row.addSpacing(15)
        self.bass_toggle = QPushButton("Slash /")
        self.bass_toggle.setCheckable(True)
        self.bass_toggle.setFixedSize(70, 32)
        self.bass_toggle.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: 1px solid #585b70;
                border-radius: 4px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #f38ba8;
                color: #1e1e2e;
                border: 1px solid #f38ba8;
            }
        """)
        self.bass_toggle.toggled.connect(self._toggle_bass_row)
        category_row.addWidget(self.bass_toggle)

        category_row.addStretch()
        layout.addLayout(category_row)
        
                
        # Bass note selector row (hidden until / Bass is toggled)
        self.bass_row = QHBoxLayout()
        self.bass_row_widget = QWidget()
        bass_row_inner = QHBoxLayout(self.bass_row_widget)
        bass_row_inner.setContentsMargins(0, 0, 0, 0)
        bass_row_inner.addWidget(QLabel("Bass:"))
        self.bass_group = QButtonGroup(self)
        self.bass_group.setExclusive(False)
        self._bass_buttons: list[QPushButton] = []
        for pc in range(12):
            btn = QPushButton(note_name(pc))
            btn.setCheckable(True)
            btn.setFixedWidth(45)
            self.bass_group.addButton(btn, pc)
            bass_row_inner.addWidget(btn)
            self._bass_buttons.append(btn)
        self.bass_clear = QPushButton("✕")
        self.bass_clear.setFixedWidth(35)
        self.bass_clear.clicked.connect(self._clear_bass)
        bass_row_inner.addWidget(self.bass_clear)
        bass_row_inner.addStretch()
        self.bass_row_widget.setVisible(False)
        layout.addWidget(self.bass_row_widget)
        
        # Quality buttons (will change based on category selection)
        self.quality_row = QHBoxLayout()
        self.quality_group = QButtonGroup(self)
        self.quality_buttons: list[QPushButton] = []
        
        layout.addLayout(self.quality_row)
        
        # Set default category and update quality buttons
        first_category = list(QUALITY_CATEGORIES.keys())[0]
        self.category_buttons[first_category].setChecked(True)
        self.category_group.buttonClicked.connect(self._update_quality_buttons)
        self._update_quality_buttons()

        # ── Current progression display (chip row) ──
        progression_header = QLabel("Progression:")
        progression_header.setStyleSheet("font-size: 13pt; padding: 4px 10px;")
        layout.addWidget(progression_header)

        self.progression_list = QListWidget()
        self.progression_list.setFlow(QListView.Flow.LeftToRight)
        self.progression_list.setWrapping(True)
        self.progression_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.progression_list.setMovement(QListView.Movement.Snap)
        self.progression_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.progression_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.progression_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.progression_list.setSpacing(6)
        self.progression_list.setFixedHeight(80)
        self.progression_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item:selected {
                background: transparent;
            }
        """)
        # Detect drag-drop reorder
        self.progression_list.model().rowsMoved.connect(self._on_chips_reordered)
        layout.addWidget(self.progression_list)

        # Empty-state placeholder label (shown when no chords)
        self.progression_empty_label = QLabel("(empty — add chords above)")
        self.progression_empty_label.setStyleSheet("color: #6c7086; font-style: italic; padding: 4px 10px;")
        layout.addWidget(self.progression_empty_label)

        # Key analysis label (kept separate)
        self.key_label = QLabel("")
        self.key_label.setStyleSheet("color: #89b4fa; font-size: 11pt; padding: 4px 10px;")
        self.key_label.setWordWrap(True)
        layout.addWidget(self.key_label)

        # ── Find scales button ──
        self.find_btn = QPushButton("Find Matching Scales")
        self.find_btn.clicked.connect(self._find_scales)
        layout.addWidget(self.find_btn)
        
        # ── Progression playback controls ──
        progression_controls = QHBoxLayout()
        
        self.play_progression_btn = QPushButton("▶ Play Progression")
        self.play_progression_btn.clicked.connect(self._play_progression)
        self.play_progression_btn.setFixedHeight(40)
        progression_controls.addWidget(self.play_progression_btn)
        
        self.stop_progression_btn = QPushButton("■ Stop Progression")
        self.stop_progression_btn.clicked.connect(self._stop_progression)
        self.stop_progression_btn.setFixedHeight(40)
        self.stop_progression_btn.setEnabled(False)  # Disabled until progression plays
        progression_controls.addWidget(self.stop_progression_btn)
        
        progression_controls.addWidget(QLabel("Tempo:"))
        from PySide6.QtWidgets import QSpinBox
        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(40, 240)
        self.tempo_spin.setValue(120)
        self.tempo_spin.setSuffix(" BPM")
        self.tempo_spin.valueChanged.connect(self._on_tempo_changed)
        progression_controls.addWidget(self.tempo_spin)

        progression_controls.addWidget(QLabel("Style:"))
        from PySide6.QtWidgets import QComboBox
        self.style_combo = QComboBox()
        for style_name in STYLE_PRESETS.keys():
            self.style_combo.addItem(style_name.replace("_", " ").title(), style_name)
        progression_controls.addWidget(self.style_combo)

        from PySide6.QtWidgets import QCheckBox
        self.loop_progression = QCheckBox("Loop")
        progression_controls.addWidget(self.loop_progression)

        self.click_track = QCheckBox("Click")
        self.click_track.setChecked(True)
        progression_controls.addWidget(self.click_track)
        
        progression_controls.addStretch()
        layout.addLayout(progression_controls)

        # ── Results (tabbed: whole-progression view + per-chord view) ──
        results_group = QGroupBox("Scale Suggestions")
        results_layout = QVBoxLayout(results_group)

        self.results_tabs = QTabWidget()
        results_layout.addWidget(self.results_tabs)

        # Tab 1: Whole Progression — the original coverage-based scale list.
        # Answers "what single scale covers the most chord tones across the
        # whole progression?" Existing behavior, untouched.
        whole_prog_tab = QWidget()
        whole_prog_layout = QVBoxLayout(whole_prog_tab)
        whole_prog_layout.setContentsMargins(4, 4, 4, 4)
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._on_scale_clicked)
        whole_prog_layout.addWidget(self.results_list)
        self.results_tabs.addTab(whole_prog_tab, "Whole Progression")

        # Tab 2: Per Chord — the chord-scale coach view. Answers "for each
        # chord, what scales should I play while that chord is sounding?"
        # Per-chord sections with idiom filter, expandable suggestions and
        # per-option info layer. Built across Pieces 2-3; for now just a
        # placeholder so the tab structure is visible and clickable.
        per_chord_tab = QWidget()
        per_chord_outer_layout = QVBoxLayout(per_chord_tab)
        per_chord_outer_layout.setContentsMargins(4, 4, 4, 4)

        # Scroll area so long progressions don't blow out the panel height
        self.per_chord_scroll = QScrollArea()
        self.per_chord_scroll.setWidgetResizable(True)
        self.per_chord_scroll.setFrameShape(QFrame.Shape.NoFrame)
        per_chord_outer_layout.addWidget(self.per_chord_scroll)

        # The container widget INSIDE the scroll area. Piece 2 will populate
        # self.per_chord_container.layout() with per-chord sections.
        self.per_chord_container = QWidget()
        self.per_chord_container_layout = QVBoxLayout(self.per_chord_container)
        self.per_chord_container_layout.setContentsMargins(0, 0, 0, 0)
        self.per_chord_container_layout.setSpacing(6)

        # Placeholder visible until Find Matching Scales has been clicked
        self.per_chord_placeholder = QLabel(
            "(Build a progression and click 'Find Matching Scales' "
            "to see per-chord scale advice.)"
        )
        self.per_chord_placeholder.setStyleSheet(
            "color: #6c7086; font-style: italic; padding: 20px;"
        )
        self.per_chord_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.per_chord_container_layout.addWidget(self.per_chord_placeholder)
        self.per_chord_container_layout.addStretch()

        self.per_chord_scroll.setWidget(self.per_chord_container)
        self._active_idiom_filters: set[str] = set()
        self._all_option_rows: list[tuple[_ScaleOptionRow, list[str]]] = []
        self.results_tabs.addTab(per_chord_tab, "Per Chord")

        layout.addWidget(results_group)

    def _chord_midi_notes(self) -> list[int]:
        root = self.root_group.checkedId()
        category_id = self.category_group.checkedId()
        category_name = list(QUALITY_CATEGORIES.keys())[category_id]
        quality_id = self.quality_group.checkedId()
        quality = QUALITY_CATEGORIES[category_name][quality_id]
        from core.music_theory import CHORD_FORMULAS
        intervals = CHORD_FORMULAS[quality]
        base = 60 + root
        notes = []
        for i, interval in enumerate(intervals):
            note = base + interval
            if i > 0 and note <= notes[-1]:
                note += 12
            notes.append(note)
        return notes
    
    def _play_chord(self) -> None:
        if self.audio and self.audio.is_ready:
            notes = self._chord_midi_notes()
            self.audio.play_chord_async(PIANO_CHANNEL, notes, duration=1.5)
            
    def _play_arpeggio(self) -> None:
        if self.audio and self.audio.is_ready:
            notes = self._chord_midi_notes()
            self.audio.play_arpeggio_async(PIANO_CHANNEL, notes)
            
    def _stop(self) -> None:
        if self.audio and self.audio.is_ready:
            self.audio.all_notes_off()
        if self.playback:
            self.playback.stop()

    # ── Save / Load progression ──────────────────────────────────────

    def _settings(self) -> QSettings:
        """QSettings handle for app-wide persistent settings (last-used dir etc.)."""
        return QSettings("MusicTheoryApp", "ScaleFinder")

    def _last_save_dir(self) -> str:
        """Directory the file dialog opens to. Persists last-used location across
        sessions. Falls back to user's Documents if no last-used dir is recorded.

        QSettings.value() returns object in Pylance's stubs even with type=str,
        so we coerce explicitly and validate as a real string before use.
        """
        raw = self._settings().value("last_save_dir", "")
        recorded = raw if isinstance(raw, str) else ""
        if recorded and os.path.isdir(recorded):
            return recorded
        return QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )

    def _remember_save_dir(self, filepath: str) -> None:
        """Record the directory the user just saved/loaded from."""
        directory = os.path.dirname(filepath)
        if directory:
            self._settings().setValue("last_save_dir", directory)

    def _save_progression(self) -> None:
        """Save the current progression to a JSON file via Windows file dialog.
        File contains chord symbols + a user-supplied name + metadata.
        Records the saved-file path to the library index for the Saved tab."""
        if not self.progression.chords:
            QMessageBox.information(
                self, "Nothing to save",
                "Build a progression first, then save it.",
            )
            return

        # Ask for a friendly name (defaults to progression's chord summary)
        default_name = " - ".join(c.display_name for c in self.progression.chords[:4])
        if len(self.progression.chords) > 4:
            default_name += " ..."
        name, ok = QInputDialog.getText(
            self, "Save Progression",
            "Name this progression:",
            text=default_name,
        )
        if not ok:
            return
        name = name.strip() or "Untitled Progression"

        # File dialog — defaults to last-used directory
        suggested_filename = self._sanitize_filename(name) + ".json"
        default_path = os.path.join(self._last_save_dir(), suggested_filename)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Progression",
            default_path,
            "Progression files (*.json);;All files (*)",
        )
        if not filepath:
            return
        # Ensure .json extension
        if not filepath.lower().endswith(".json"):
            filepath += ".json"

        data = {
            "format": "music-theory-progression-v1",
            "name": name,
            "chords": [c.display_name for c in self.progression.chords],
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            QMessageBox.critical(
                self, "Save failed",
                f"Could not write to {filepath}:\n{exc}",
            )
            return

        self._remember_save_dir(filepath)
        # Register in the library index (Piece 1.5b will define this).
        self._register_in_library(filepath, name, len(data["chords"]))
        self.status_message(f"Saved: {name}")

    def _load_progression(self) -> None:
        """Load a progression from a JSON file via Windows file dialog.
        Replaces the current progression."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Progression",
            self._last_save_dir(),
            "Progression files (*.json);;All files (*)",
        )
        if not filepath:
            return
        self.load_progression_from_file(filepath)

    def load_progression_from_file(self, filepath: str) -> bool:
        """Load a progression from a specific file. Public so the Saved tab
        (Piece 1.5c) can call it directly when the user clicks Load there.
        Returns True on success."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(
                self, "Load failed",
                f"Could not read {filepath}:\n{exc}",
            )
            return False

        if not isinstance(data, dict) or "chords" not in data:
            QMessageBox.critical(
                self, "Load failed",
                f"{filepath} is not a valid progression file.",
            )
            return False

        chord_symbols = data.get("chords", [])
        new_chords: list[Chord] = []
        for sym in chord_symbols:
            try:
                new_chords.append(Chord.parse(sym))
            except (ValueError, KeyError) as exc:
                QMessageBox.warning(
                    self, "Load warning",
                    f"Skipped unrecognized chord '{sym}': {exc}",
                )

        if not new_chords:
            QMessageBox.warning(
                self, "Load warning",
                "No valid chords found in the file.",
            )
            return False

        self.progression = ChordProgression(chords=new_chords)
        self._update_display()
        self.results_list.clear()
        self.progression_changed.emit(self.progression)
        self._remember_save_dir(filepath)
        name = data.get("name", os.path.splitext(os.path.basename(filepath))[0])
        self.status_message(f"Loaded: {name}")
        # Register in library if it isn't already (e.g., loading a file from
        # outside the library). Piece 1.5b implements the registration.
        self._register_in_library(filepath, name, len(new_chords))
        return True

    def _sanitize_filename(self, name: str) -> str:
        """Strip characters that would be invalid in a Windows filename."""
        bad = '<>:"/\\|?*'
        cleaned = "".join("_" if c in bad else c for c in name).strip()
        return cleaned or "progression"

    def status_message(self, msg: str) -> None:
        """Push a short message to the main window status bar.
        Walks up the parent chain to find the QMainWindow (parent of parent
        of ... — we don't take a direct reference)."""
        from PySide6.QtWidgets import QMainWindow
        widget = self.parent()
        while widget is not None and not isinstance(widget, QMainWindow):
            widget = widget.parent()
        if widget is not None and widget.statusBar() is not None:
            widget.statusBar().showMessage(msg, 5000)

    def _register_in_library(self, filepath: str, name: str, n_chords: int) -> None:
        """Add or update an entry in the saved-progressions library index.
        Index files live one-per-directory alongside the saved files
        themselves. See gui/saved_library.py for details."""
        from gui.saved_library import register_save
        register_save(filepath, name, n_chords)

    def _toggle_bass_row(self, checked: bool) -> None:
        self.bass_row_widget.setVisible(checked)
        if not checked:
            self._clear_bass()

    def _clear_bass(self) -> None:
        self.bass_group.setExclusive(False)
        for btn in self._bass_buttons:
            btn.setChecked(False)
        self.bass_group.setExclusive(False)

    def _selected_bass(self) -> Optional[int]:
        for btn in self._bass_buttons:
            if btn.isChecked():
                return self.bass_group.id(btn)
        return None
    
    def _add_chord(self) -> None:
        root = GUITAR_NAMES[self.root_group.checkedId()]
        # Get selected category and quality
        category_id = self.category_group.checkedId()
        category_name = list(QUALITY_CATEGORIES.keys())[category_id]
        quality_id = self.quality_group.checkedId()
        quality = QUALITY_CATEGORIES[category_name][quality_id]
        symbol = root + QUALITY_DISPLAY.get(quality, quality or "maj")
        bass = self._selected_bass()
        if bass is not None:
            symbol += "/" + note_name(bass)

        chord = Chord.parse(symbol)
        self.progression.chords.append(chord)
        self._update_display()
        self.progression_changed.emit(self.progression)

    def _clear_progression(self):
        self.progression = ChordProgression()
        self._update_display()
        self.results_list.clear()
        self.progression_changed.emit(self.progression)

    def _update_display(self):
        """Update progression display without highlighting."""
        self._update_progression_display()
    
    def _update_progression_display(self, current_index: int | None = None):
        """Update progression display with chord chips."""
        # Clear existing chips
        self.progression_list.clear()

        if not self.progression.chords:
            self.progression_list.setVisible(False)
            self.progression_empty_label.setVisible(True)
            self.key_label.setText("")
            return

        self.progression_list.setVisible(True)
        self.progression_empty_label.setVisible(False)

        # Compute Roman labels if we have enough chords
        roman_labels: list[str] = []
        if len(self.progression.chords) >= 2:
            ka = analyze_key(self.progression)
            if ka is not None:
                rl = analyze_roman(self.progression, ka)
                roman_labels = [r.numeral for r in rl]

        # Build a chip for each chord
        for i, chord in enumerate(self.progression.chords):
            display = chord.display_name
            if current_index is not None and i == current_index:
                display = f"▶ {display}"

            roman = roman_labels[i] if i < len(roman_labels) else ""
            chip = ChordChip(display, roman=roman)
            chip.chord_index = i
            chip.delete_requested.connect(self._on_chip_delete)
            chip.right_clicked.connect(self._on_chip_right_click)

            item = QListWidgetItem()
            item.setSizeHint(chip.sizeHint() + QSize(8, 12))
            self.progression_list.addItem(item)
            self.progression_list.setItemWidget(item, chip)

        # Update key analysis
        if len(self.progression.chords) >= 2:
            analysis = analyze_key(self.progression)
            if analysis and analysis.confidence >= 0.7:
                lines = [f"Key: {analysis.display}"]
                scale_names = [s.display_name for s in analysis.parent_scales]
                if len(scale_names) > 1:
                    lines.append(f"Scales in play: {' + '.join(scale_names)}")
                for note in analysis.notes:
                    lines.append(f"— {note}")
                self.key_label.setText("\n".join(lines))
            else:
                self.key_label.setText("")
        else:
            self.key_label.setText("")

    def _find_scales(self):
        if not self.progression.chords:
            return

        # Populate the whole-progression tab (existing behavior, unchanged)
        self._populate_whole_progression_tab()

        # Populate the per-chord tab using analyze_chord_scales()
        self._populate_per_chord_tab()

    def _populate_whole_progression_tab(self) -> None:
        """Fill the whole-progression results list. Shows key-analyzer scales
        first (the musically correct answer), then coverage-based matches."""
        self.results_list.clear()

        ka = analyze_key(self.progression)
        if ka is not None and ka.parent_scales:
            self.results_list.addItem("── Key Scales ──")
            for scale in ka.parent_scales:
                m = match_scale(self.progression, scale)
                item = QListWidgetItem(f"  {m.display_name}")
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.results_list.addItem(item)
            self.results_list.addItem("")

        results = suggest_scales(self.progression, top_n=3, alternatives=5)

        self.results_list.addItem("── Coverage Matches ──")
        for m in results["top"]:
            miss = f"  (missing: {', '.join(m.missing_note_names())})" if m.missing_notes else "  ✓"
            item = QListWidgetItem(f"  {m.display_name}   score: {m.score:.0%}{miss}")
            item.setData(Qt.ItemDataRole.UserRole, m)
            self.results_list.addItem(item)

        self.results_list.addItem("")
        self.results_list.addItem("── Alternatives ──")
        for m in results["alternatives"]:
            miss = f"  (missing: {', '.join(m.missing_note_names())})" if m.missing_notes else "  ✓"
            item = QListWidgetItem(f"  {m.display_name}   score: {m.score:.0%}{miss}")
            item.setData(Qt.ItemDataRole.UserRole, m)
            self.results_list.addItem(item)

    def _populate_per_chord_tab(self) -> None:
        """Fill the per-chord tab using the chord-scale coach.

        Uses analyze_key_sections() for section-aware key detection so
        modulating progressions show per-section divider headers. Falls
        back to analyze_key() if section analysis returns None.
        """
        
        # Clear out the existing container contents (placeholder or prior render)
        while self.per_chord_container_layout.count() > 0:
            item = self.per_chord_container_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        # Get key analysis. Try section-aware first; fall back to single-key.
        ka = analyze_key_sections(self.progression)
        if ka is None:
            ka = analyze_key(self.progression)
        if ka is None:
            # No key could be determined — show a placeholder
            msg = QLabel(
                "(Could not analyze the key for this progression — "
                "scale advice unavailable.)"
            )
            msg.setStyleSheet(
                "color: #6c7086; font-style: italic; padding: 20px;"
            )
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.per_chord_container_layout.addWidget(msg)
            self.per_chord_container_layout.addStretch()
            return
        
        # Get Roman labels and per-chord scale advice
        roman_labels = analyze_roman(self.progression, ka)
        advice = analyze_chord_scales(self.progression, ka, roman_labels)

        # Idiom filter row
        self._active_idiom_filters.clear()
        self._all_option_rows.clear()
        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(4, 4, 4, 4)
        filter_layout.setSpacing(6)
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet(
            "color: #a6adc8; font-size: 10pt; background: transparent;"
        )
        filter_layout.addWidget(filter_label)

        self._idiom_pills: dict[str, QLabel] = {}
        for idiom in ALL_IDIOMS:
            pill = QLabel(idiom.replace("_", " "))
            color = IDIOM_COLORS.get(idiom, "#6c7086")
            pill.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    background-color: rgba(180, 190, 254, 20);
                    border: 1px solid {color};
                    border-radius: 8px;
                    padding: 3px 10px;
                    font-size: 9pt;
                    font-weight: bold;
                }}
            """)
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.mousePressEvent = lambda e, i=idiom: self._toggle_idiom_filter(i)
            filter_layout.addWidget(pill)
            self._idiom_pills[idiom] = pill

        filter_layout.addStretch()
        self.per_chord_container_layout.addWidget(filter_row)
        

        # Build a map of section start indices → section, so we can emit
        # a section divider header at the right points (multi-section only).
        section_starts = {}
        if ka.sections and len(ka.sections) > 1:
            for section in ka.sections:
                section_starts[section.start_index] = section

        # Render one section per chord, interleaved with section dividers
        for i, (chord, rl, adv) in enumerate(zip(
            self.progression.chords, roman_labels, advice
        )):
            # Section divider above this chord, if it's a section boundary
            if i in section_starts:
                section = section_starts[i]
                self._add_section_divider(section)

            chord_section = _ChordAdviceSection(
                chord_display=chord.display_name,
                roman_numeral=rl.numeral,
                options=adv.options,
                chord_obj=chord,
            )
            self.per_chord_container_layout.addWidget(chord_section)

            for row in chord_section.findChildren(_ScaleOptionRow):
                self._all_option_rows.append((row, row.option.idioms))

        # Stretch at the bottom so sections pack to the top
        self.per_chord_container_layout.addStretch()

    def _add_section_divider(self, section) -> None:
        """Add a visual divider with the section's key label to the
        per-chord container. Used for modulating progressions."""
        divider_widget = QWidget()
        divider_layout = QHBoxLayout(divider_widget)
        divider_layout.setContentsMargins(0, 12, 0, 4)
        divider_layout.setSpacing(8)

        # Left hairline
        left_line = QFrame()
        left_line.setFrameShape(QFrame.Shape.HLine)
        left_line.setStyleSheet("color: #45475a; background-color: #45475a; max-height: 1px;")
        divider_layout.addWidget(left_line, 1)

        # Section label
        label_text = (
            f"Bars {section.start_index + 1}–{section.end_index + 1}: "
            f"{section.tonic_name} {section.mode_label}"
        )
        section_label = QLabel(label_text)
        section_label.setStyleSheet(
            "color: #89b4fa; font-size: 10pt; font-weight: bold; "
            "background: transparent; padding: 0 8px;"
        )
        divider_layout.addWidget(section_label)

        # Right hairline
        right_line = QFrame()
        right_line.setFrameShape(QFrame.Shape.HLine)
        right_line.setStyleSheet("color: #45475a; background-color: #45475a; max-height: 1px;")
        divider_layout.addWidget(right_line, 1)

        self.per_chord_container_layout.addWidget(divider_widget)

    def _toggle_idiom_filter(self, idiom: str) -> None:
        if idiom in self._active_idiom_filters:
            self._active_idiom_filters.discard(idiom)
        else:
            self._active_idiom_filters.add(idiom)

        for tag, pill in self._idiom_pills.items():
            color = IDIOM_COLORS.get(tag, "#6c7086")
            if tag in self._active_idiom_filters:
                pill.setStyleSheet(f"""
                    QLabel {{
                        color: #1e1e2e;
                        background-color: {color};
                        border: 1px solid {color};
                        border-radius: 8px;
                        padding: 3px 10px;
                        font-size: 9pt;
                        font-weight: bold;
                    }}
                """)
            else:
                pill.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        background-color: rgba(180, 190, 254, 20);
                        border: 1px solid {color};
                        border-radius: 8px;
                        padding: 3px 10px;
                        font-size: 9pt;
                        font-weight: bold;
                    }}
                """)

        for row, idioms in self._all_option_rows:
            if not self._active_idiom_filters:
                row.setVisible(True)
            else:
                row.setVisible(bool(self._active_idiom_filters & set(idioms)))
    
    def _on_chip_right_click(self, chord_idx: int) -> None:
        from PySide6.QtWidgets import QMenu
        if chord_idx < 0 or chord_idx >= len(self.progression.chords):
            return

        chord = self.progression.chords[chord_idx]

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
            QMenu::separator {
                height: 1px;
                background: #45475a;
                margin: 4px 8px;
            }
        """)

        tone_names = ", ".join(note_name(pc) for pc in chord.pitch_classes)
        chord_tone_action = menu.addAction(f"Chord tones ({tone_names})")
        chord_tone_action.setData(("chord", chord))

        menu.addSeparator()

        ka = analyze_key(self.progression)
        if ka is not None:
            roman_labels = analyze_roman(self.progression, ka)
            advice = analyze_chord_scales(self.progression, ka, roman_labels)
            if chord_idx < len(advice):
                for opt in advice[chord_idx].options[:5]:
                    action = menu.addAction(opt.scale.display_name)
                    action.setData(("scale", opt))

        chosen = menu.exec(self.cursor().pos())
        if chosen is not None:
            data = chosen.data()
            if data[0] == "chord":
                self.chord_tones_selected.emit(data[1])
            elif data[0] == "scale":
                from core.scale_matcher import match_scale
                m = match_scale(self.progression, data[1].scale)
                self.scale_selected.emit(m)
    
    def _on_scale_clicked(self, item) -> None:
        match = item.data(Qt.ItemDataRole.UserRole)
        if match is not None:
            self.scale_selected.emit(match)
            
    def _update_quality_buttons(self) -> None:
        """Update quality buttons based on selected category."""
        # Clear existing quality buttons
        for btn in self.quality_buttons:
            self.quality_group.removeButton(btn)
            self.quality_row.removeWidget(btn)
            btn.deleteLater()
        self.quality_buttons.clear()
        
        # Get selected category
        category_id = self.category_group.checkedId()
        category_name = list(QUALITY_CATEGORIES.keys())[category_id]
        qualities = QUALITY_CATEGORIES[category_name]
        
        # Create new quality buttons
        for i, quality_key in enumerate(qualities):
            full_name = QUALITY_FULL_NAMES.get(quality_key, quality_key)
            btn = QPushButton(full_name)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            self.quality_group.addButton(btn, i)
            self.quality_buttons.append(btn)
            self.quality_row.addWidget(btn)
        
        # Select first quality by default
        if self.quality_buttons:
            self.quality_buttons[0].setChecked(True)   
    
    def _play_progression(self) -> None:
        """Play the progression using the PlaybackEngine."""
        if not self.progression.chords:
            return
        if not self.playback:
            return

        self.play_progression_btn.setEnabled(False)
        self.stop_progression_btn.setEnabled(True)

        style = self.style_combo.currentData()
        self.playback.play_progression(
            progression=self.progression,
            tempo=self.tempo_spin.value(),
            style=style,
            click_track=self.click_track.isChecked(),
            loop=self.loop_progression.isChecked(),
            transpose=-1,
        )
    
    def _stop_progression(self) -> None:
        """Stop progression playback."""
        if self.playback:
            self.playback.stop()
        self.stop_progression_btn.setEnabled(False)
        self.play_progression_btn.setEnabled(True)
        self._update_progression_display()
        
    def _on_tempo_changed(self, bpm: int) -> None:
        """Update tempo live during playback."""
        if self.playback and self.playback.is_playing():
            self.playback.set_tempo(bpm)
            
    def _on_chip_delete(self, chip: ChordChip):
        """User clicked × on a chord chip."""
        # Find which row this chip corresponds to
        for row in range(self.progression_list.count()):
            item = self.progression_list.item(row)
            if self.progression_list.itemWidget(item) is chip:
                # Remove from the underlying data
                del self.progression.chords[row]
                # Rerender
                self._update_progression_display()
                self.progression_changed.emit(self.progression)
                break

    def _on_chips_reordered(self, *args):
        """User dragged a chip to a new position. Resync self.progression.chords."""
        new_chords = []
        for row in range(self.progression_list.count()):
            item = self.progression_list.item(row)
            chip = self.progression_list.itemWidget(item)
            if not isinstance(chip, ChordChip):
                continue
            if chip is None:
                continue
            # Match the chip's display text back to a chord
            # Strip any "▶ " prefix from playback highlighting
            display = chip.chord_display.replace("▶ ", "").strip()
            # Find matching chord object (by display name, in current progression)
            # Since display names are unique-ish but could repeat, we consume them in order
            for idx, c in enumerate(self.progression.chords):
                if c.display_name == display and c not in new_chords[:]:
                    new_chords.append(c)
                    break

        # If something went weird (count mismatch), bail out and just rerender from current data
        if len(new_chords) != len(self.progression.chords):
            self._update_progression_display()
            return

        self.progression.chords = new_chords
        # Rerender to be consistent (no infinite loop — chip count matches)
        self._update_progression_display()
        self.progression_changed.emit(self.progression)    