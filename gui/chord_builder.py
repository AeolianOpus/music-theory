from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QListWidget, QGroupBox,
)
from PySide6.QtCore import Signal

from core.music_theory import Chord, ChordProgression, SHARP_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY
from core.scale_matcher import suggest_scales


class ChordBuilder(QWidget):
    # Signal other widgets can listen to (fretboard, piano, etc.)
    progression_changed = Signal(object)   # emits ChordProgression
    scale_selected = Signal(object)        # emits ScaleMatch
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progression = ChordProgression()
        self._setup_ui()
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── Chord input row ──
        input_row = QHBoxLayout()

        # Root note dropdown
        self.root_combo = QComboBox()
        self.root_combo.addItems(SHARP_NAMES)  # C, C#, D, ... B
        input_row.addWidget(QLabel("Root:"))
        input_row.addWidget(self.root_combo)

        # Quality dropdown
        self.quality_combo = QComboBox()
        for key, display in QUALITY_DISPLAY.items():
            label = display if display else "maj"
            self.quality_combo.addItem(label, key)  # shows "m", stores "min"
        input_row.addWidget(QLabel("Quality:"))
        input_row.addWidget(self.quality_combo)

        # Add button
        self.add_btn = QPushButton("Add Chord")
        self.add_btn.clicked.connect(self._add_chord)
        input_row.addWidget(self.add_btn)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_progression)
        input_row.addWidget(self.clear_btn)

        layout.addLayout(input_row)

        # ── Current progression display ──
        self.progression_label = QLabel("Progression: (empty)")
        self.progression_label.setStyleSheet("font-size: 16px; padding: 10px;")
        layout.addWidget(self.progression_label)

        # ── Find scales button ──
        self.find_btn = QPushButton("Find Matching Scales")
        self.find_btn.clicked.connect(self._find_scales)
        layout.addWidget(self.find_btn)

        # ── Results ──
        results_group = QGroupBox("Scale Suggestions")
        results_layout = QVBoxLayout(results_group)

        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._on_scale_clicked)
        results_layout.addWidget(self.results_list)

        layout.addWidget(results_group)

    def _add_chord(self):
        root = self.root_combo.currentText()
        quality = self.quality_combo.currentData()
        symbol = root + QUALITY_DISPLAY.get(quality, quality or "maj")

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
        if self.progression.chords:
            text = self.progression.display()
        else:
            text = "(empty)"
        self.progression_label.setText(f"Progression: {text}")

    def _find_scales(self):
        if not self.progression.chords:
            return

        self.results_list.clear()
        results = suggest_scales(self.progression, top_n=3, alternatives=5)

        # Store matches for click handling
        self._matches = []

        self.results_list.addItem("── Top Matches ──")
        for m in results["top"]:
            self._matches.append(m)
            miss = f"  (missing: {', '.join(m.missing_note_names())})" if m.missing_notes else "  ✓"
            self.results_list.addItem(
                f"  {m.display_name}   score: {m.score:.0%}{miss}"
            )

        self.results_list.addItem("")
        self.results_list.addItem("── Alternatives ──")
        for m in results["alternatives"]:
            self._matches.append(m)
            miss = f"  (missing: {', '.join(m.missing_note_names())})" if m.missing_notes else "  ✓"
            self.results_list.addItem(
                f"  {m.display_name}   score: {m.score:.0%}{miss}"
            )

    def _on_scale_clicked(self, item):
        # TODO: emit selected scale so fretboard/piano can highlight it
        pass