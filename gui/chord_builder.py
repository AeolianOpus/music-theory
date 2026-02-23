from unicodedata import category

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QListWidget, QGroupBox, QListWidgetItem, QButtonGroup,
)
from PySide6.QtCore import Signal, Qt

from core.audio_engine import AudioEngine, PIANO_CHANNEL
from core.music_theory import QUALITY_FULL_NAMES, Chord, ChordProgression, SHARP_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY, QUALITY_FULL_NAMES
from core.scale_matcher import suggest_scales

# Chord quality categories for button layout
QUALITY_CATEGORIES = {
    "Triads": ["maj", "min", "dim", "aug"],
    "7ths": ["maj7", "min7", "7", "dim7", "m7b5", "minmaj7", "aug7", "augmaj7"],
    "Extended": ["9", "maj9", "min9", "11", "min11", "13", "min13"],
    "Altered": ["7b5", "7#5", "7b9", "7#9", "add9", "madd9"],
    "Sus & Other": ["sus2", "sus4", "6", "min6", "5"],
}

class ChordBuilder(QWidget):
    # Signal other widgets can listen to (fretboard, piano, etc.)
    progression_changed = Signal(object)   # emits ChordProgression
    scale_selected = Signal(object)        # emits ScaleMatch
    
    def __init__(self, audio_engine: AudioEngine | None = None, parent=None):
        super().__init__(parent)
        self.progression = ChordProgression()
        self.audio = audio_engine
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
        for i, name in enumerate(SHARP_NAMES):
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
        self.clear_btn.setFixedHeight(50)
        self.clear_btn.setMinimumWidth(120)
        input_row.addWidget(self.clear_btn)

        input_row.addStretch()  # Separate from playback controls

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
        
        category_row.addStretch()
        layout.addLayout(category_row)
        
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

    def _add_chord(self) -> None:
        root = SHARP_NAMES[self.root_group.checkedId()]
        # Get selected category and quality
        category_id = self.category_group.checkedId()
        category_name = list(QUALITY_CATEGORIES.keys())[category_id]
        quality_id = self.quality_group.checkedId()
        quality = QUALITY_CATEGORIES[category_name][quality_id]
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
        self.results_list.addItem("── Top Matches ──")
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