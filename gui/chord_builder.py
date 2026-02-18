from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QListWidget, QGroupBox, QListWidgetItem, QButtonGroup,
)
from PySide6.QtCore import Signal, Qt

from core.audio_engine import AudioEngine, PIANO_CHANNEL
from core.music_theory import Chord, ChordProgression, SHARP_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY
from core.scale_matcher import suggest_scales


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

        # Root note dropdown
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

        # Play button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self._play_chord)
        input_row.addWidget(self.play_btn)

        # Arpeggio button
        self.arp_btn = QPushButton("🎵 Arpeggio")
        self.arp_btn.clicked.connect(self._play_arpeggio)
        input_row.addWidget(self.arp_btn)

        # Stop button
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self._stop)
        input_row.addWidget(self.stop_btn)
        
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

    def _chord_midi_notes(self) -> list[int]:
        root = self.root_group.checkedId()
        quality = self.quality_combo.currentData()
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