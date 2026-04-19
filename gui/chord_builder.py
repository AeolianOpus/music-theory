from unicodedata import category

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QListWidget, QGroupBox, QListWidgetItem, QButtonGroup,
)
from PySide6.QtCore import Signal, Qt

from core.audio_engine import AudioEngine, PIANO_CHANNEL
from core.music_theory import QUALITY_FULL_NAMES, Chord, ChordProgression, SHARP_NAMES, GUITAR_NAMES, CHORD_FORMULAS, QUALITY_DISPLAY, QUALITY_FULL_NAMES, note_name
from core.scale_matcher import suggest_scales, detect_key

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

class ChordBuilder(QWidget):
    # Signal other widgets can listen to (fretboard, piano, etc.)
    progression_changed = Signal(object)   # emits ChordProgression
    scale_selected = Signal(object)        # emits ScaleMatch
    
    def __init__(self, audio_engine: AudioEngine | None = None, parent=None):
        super().__init__(parent)
        self.progression = ChordProgression()
        self.audio = audio_engine
        self.is_playing_progression = False  # Track progression playback state
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
        self.key_label = QLabel("")
        self.progression_label.setStyleSheet("font-size: 16px; padding: 10px;")
        self.key_label.setStyleSheet("color: #89b4fa; font-size: 11pt; padding: 4px;")
        layout.addWidget(self.progression_label)
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
        
        progression_controls.addWidget(QLabel("Chord Duration:"))
        from PySide6.QtWidgets import QSpinBox
        self.chord_duration = QSpinBox()
        self.chord_duration.setRange(500, 5000)  # 0.5 to 5 seconds
        self.chord_duration.setValue(1500)  # Default 1.5 seconds
        self.chord_duration.setSuffix(" ms")
        progression_controls.addWidget(self.chord_duration)
        
        from PySide6.QtWidgets import QCheckBox
        self.loop_progression = QCheckBox("Loop")
        progression_controls.addWidget(self.loop_progression)
        
        # Add rhythm pattern selector
        progression_controls.addWidget(QLabel("Pattern:"))
        from PySide6.QtWidgets import QComboBox
        self.rhythm_pattern = QComboBox()
        for pattern_name in RHYTHM_PATTERNS.keys():
            self.rhythm_pattern.addItem(pattern_name)
        progression_controls.addWidget(self.rhythm_pattern)
        
        progression_controls.addStretch()
        layout.addLayout(progression_controls)

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
        
        # Stop progression playback
        self.is_playing_progression = False     

    def _add_chord(self) -> None:
        root = GUITAR_NAMES[self.root_group.checkedId()]
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
        """Update progression display without highlighting."""
        self._update_progression_display()
    
    def _update_progression_display(self, current_index: int | None = None):
        """Update progression display, optionally highlighting the current chord."""
        if not self.progression.chords:
            self.progression_label.setText("Progression: (empty)")
            return
        
        # Build display with optional highlighting
        chord_displays = []
        for i, chord in enumerate(self.progression.chords):
            display = chord.display_name
            if current_index is not None and i == current_index:
                # Highlight current chord
                display = f"► {display} ◄"
            chord_displays.append(display)
        
        text = " - ".join(chord_displays)
        self.progression_label.setText(f"Progression: {text}")
        
        if len(self.progression.chords) >= 3:
            key_info = detect_key(self.progression)
            print(f"DEBUG key_info: {key_info}")
            if key_info:
                # Only show if the winner is clearly ahead of the runner-up
                chord_pcs = self.progression.all_pitch_classes
                best_coverage = len(chord_pcs & key_info["scale"].pitch_class_set) / len(chord_pcs)
                alt_coverage = len(chord_pcs & key_info["alternative"].pitch_class_set) / len(chord_pcs)
                print(f"DEBUG best={best_coverage:.2f} alt={alt_coverage:.2f} diff={best_coverage-alt_coverage:.2f}")

                if best_coverage - alt_coverage >= 0.05:
                    display = key_info["display"].replace("Key of ", "")
                    self.key_label.setText(f"Tonal center: {display}")
                elif best_coverage >= 0.9:
                    # Tied — show both honestly
                    best_disp = key_info["display"].replace("Key of ", "")
                    # Format alternative too
                    alt_scale = key_info["alternative"]
                    alt_root = note_name(alt_scale.root)
                    alt_qual = "minor" if "Aeolian" in alt_scale.name else alt_scale.name
                    self.key_label.setText(f"Ambiguous: {best_disp} or {alt_root} {alt_qual}")
                else:
                    self.key_label.setText("")
            else:
                self.key_label.setText("")
        else:
            self.key_label.setText("")

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
    
    def _play_progression(self) -> None:
        """Play through the entire chord progression."""
        if not self.progression.chords:
            return
        
        if not self.audio or not self.audio.is_ready:
            return
        
        # Set playback flag
        self.is_playing_progression = True
        self.play_progression_btn.setEnabled(False)
        self.stop_progression_btn.setEnabled(True)
        
        import threading
        
        def play_sequence():
            if not self.audio:  # Extra safety check
                return
                
            audio_engine = self.audio  # Local variable for type checker
            duration_ms = self.chord_duration.value()
            duration_sec = duration_ms / 1000.0
            
            # Get rhythm pattern
            pattern_name = self.rhythm_pattern.currentText()
            pattern = RHYTHM_PATTERNS[pattern_name]
            
            while self.is_playing_progression:
                for i, chord in enumerate(self.progression.chords):
                    # Check if we should stop
                    if not self.is_playing_progression:
                        break
                    
                    # Calculate duration based on rhythm pattern
                    pattern_index = i % len(pattern)
                    chord_duration = duration_sec * pattern[pattern_index]
                    
                    # Update UI to highlight current chord
                    self._update_progression_display(current_index=i)
                    
                    # Build MIDI notes for this chord
                    root = chord.root
                    intervals = chord.intervals
                    base = 60 + root
                    notes = []
                    for idx, interval in enumerate(intervals):
                        note = base + interval
                        if idx > 0 and note <= notes[-1]:
                            note += 12
                        notes.append(note)
                    
                    # Play the chord
                    audio_engine.play_chord_async(PIANO_CHANNEL, notes, duration=chord_duration)
                    
                    # Wait for chord duration
                    import time
                    time.sleep(chord_duration)
                
                # Check if we should loop
                if not self.loop_progression.isChecked():
                    self.is_playing_progression = False
                    break
            
            # Reset display when done
            self._update_progression_display()
            self.stop_progression_btn.setEnabled(False)
            self.play_progression_btn.setEnabled(True)
        
        # Run in background thread so UI doesn't freeze
        thread = threading.Thread(target=play_sequence, daemon=True)
        thread.start()
    
    def _stop_progression(self) -> None:
        """Stop progression playback."""
        self.is_playing_progression = False
        self.stop_progression_btn.setEnabled(False)
        self.play_progression_btn.setEnabled(True)
        if self.audio and self.audio.is_ready:
            self.audio.all_notes_off()    