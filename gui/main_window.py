from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QStatusBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from core.audio_engine import AudioEngine
from core.dawdreamer_engine import DawDreamerEngine
from gui.chord_builder import ChordBuilder
from gui.saved_progressions import SavedProgressionsTab


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(
        self,
        audio_engine: AudioEngine,
        base_dir: str,
        dawdreamer_engine: DawDreamerEngine | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.audio = audio_engine
        self.daw = dawdreamer_engine
        self.base_dir = base_dir

        self.setWindowTitle("Music Theory Scale Finder")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Build the main UI layout with tabs."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setMovable(False)

        # ── Tabs (placeholders — each will be a full widget) ──
        self.chord_builder = ChordBuilder(self.audio, dawdreamer_engine=self.daw)
        self.tabs.addTab(self.chord_builder, "🎵 Scale Finder")

        from gui.fretboard import FretboardWidget

        # Add fretboard
        self.fretboard = FretboardWidget()
        self.tabs.addTab(self.fretboard, "Guitar")

        # Connect scale selection to fretboard
        self.chord_builder.scale_selected.connect(self._update_fretboard_from_scale)
        self.chord_builder.chord_tones_selected.connect(self._update_fretboard_from_chord)
        self.chord_builder.progression_changed.connect(self._update_fretboard_from_progression)

        self.tabs.addTab(self._placeholder("Piano Keyboard",
            "Interactive piano keyboard for visualizing scales and chords.\n"
            "Click keys to play notes and chords."),
            "🎹 Piano")

        self.tabs.addTab(self._placeholder("Backing Tracks",
            "Drum and bass loops to practice over.\n"
            "Choose patterns, set tempo, play along."),
            "🥁 Backing Tracks")

        self.tabs.addTab(self._placeholder("Artist Presets",
            "Signature chord progressions and scales from legendary artists.\n"
            "Yngwie, Gary Moore, Al Di Meola, Pink Floyd, Bach, and more."),
            "🎤 Artist Presets")

        self.tabs.addTab(self._placeholder("Tuning",
            "Select or customize instrument tuning.\n"
            "Shift by half steps, choose from presets, or build your own."),
            "🔧 Tuning")

        # Saved Progressions tab — library of saved chord progressions.
        # Click Load on any entry to push the progression into the
        # chord_builder and switch back to the Scale Finder tab.
        self.saved_tab = SavedProgressionsTab()
        self.saved_tab.load_progression_requested.connect(
            self._on_load_progression_from_library
        )
        self.tabs.addTab(self.saved_tab, "💾 Saved")

        layout.addWidget(self.tabs)

        # Status bar — shows both backends' readiness
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        fs_status = "🔊 FluidSynth ready" if self.audio.is_ready else "🔇 No SoundFont"
        vst_status = (
            "🎹 Kontakt ready"
            if (self.daw is not None and self.daw.is_ready)
            else "🎹 VST offline"
        )
        self.status.showMessage(f"{fs_status}  |  {vst_status}")

    def _placeholder(self, title: str, description: str) -> QWidget:
        """Create a placeholder tab widget."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_desc = QLabel(description)
        lbl_desc.setFont(QFont("Segoe UI", 12))
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setStyleSheet("color: #888;")

        lbl_status = QLabel("[ Under Construction ]")
        lbl_status.setFont(QFont("Segoe UI", 10))
        lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_status.setStyleSheet("color: #555; margin-top: 20px;")

        lay.addWidget(lbl_title)
        lay.addWidget(lbl_desc)
        lay.addWidget(lbl_status)
        return w

    def _note_positions(self, pitch_classes, root_pc=None):
        from PySide6.QtGui import QColor
        tuning = self.fretboard.tuning
        positions = set()
        colors = {}
        text_colors = {}
        ROOT_COLOR = QColor(243, 139, 168, 155)   # pink — root
        TONE_COLOR = QColor(137, 180, 250, 155)   # blue — other tones
        THIRD_TEXT = QColor(255, 50, 255)         # bright fuchsia text for 3rd
        FIFTH_TEXT = QColor(152, 255, 200)        # mint text for 5th

        third_pc = (root_pc + 3) % 12 if root_pc is not None else None
        major_third_pc = (root_pc + 4) % 12 if root_pc is not None else None
        fifth_pc = (root_pc + 7) % 12 if root_pc is not None else None

        for string_idx in range(tuning.num_strings):
            for pc in pitch_classes:
                for fret in tuning.fret_for_note(string_idx, pc):
                    pos = (string_idx, fret)
                    positions.add(pos)
                    colors[pos] = ROOT_COLOR if pc == root_pc else TONE_COLOR
                    if pc == third_pc or pc == major_third_pc:
                        text_colors[pos] = THIRD_TEXT
                    elif pc == fifth_pc:
                        text_colors[pos] = FIFTH_TEXT
        return positions, colors, text_colors

    def _update_fretboard_from_scale(self, scale_match):
        scale = scale_match.scale
        pitch_classes = set(scale_match.scale.pitch_classes)
        root_pc = scale_match.scale.root % 12
        positions, colors, text_colors = self._note_positions(pitch_classes, root_pc)
        self.fretboard.highlight_notes(positions, colors, text_colors)
        self.tabs.setCurrentWidget(self.fretboard)

    def _update_fretboard_from_chord(self, chord):
        pitch_classes = set(chord.pitch_classes)
        root_pc = chord.root % 12
        positions, colors, text_colors = self._note_positions(pitch_classes, root_pc)
        self.fretboard.highlight_notes(positions, colors, text_colors)
        self.tabs.setCurrentWidget(self.fretboard)

    def _update_fretboard_from_progression(self, progression):
        from PySide6.QtGui import QColor
        if not progression.chords:
            self.fretboard.clear_highlights()
            return
        all_pcs = set()
        root_pcs = set()
        for chord in progression.chords:
            for pc in chord.pitch_classes:
                all_pcs.add(pc % 12)
            root_pcs.add(chord.root % 12)
        positions, colors, _ = self._note_positions(all_pcs)
        ROOT_COLOR = QColor(249, 226, 175)
        tuning = self.fretboard.tuning
        for (string_idx, fret) in positions:
            pc = tuning.note_at(string_idx, fret) % 12
            if pc in root_pcs:
                colors[(string_idx, fret)] = ROOT_COLOR
        self.fretboard.highlight_notes(positions, colors)
    
    def _apply_theme(self):
        """Apply dark theme QSS."""
        self.setStyleSheet("""
        QMainWindow {
            background-color: #1e1e2e;
        }
        QTabWidget::pane {
            border: 1px solid #313244;
            background-color: #1e1e2e;
        }
        QTabBar::tab {
            background-color: #313244;
            color: #cdd6f4;
            padding: 10px 20px;
            margin-right: 2px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background-color: #45475a;
            color: #f5c2e7;
        }
        QTabBar::tab:hover {
            background-color: #585b70;
        }
        QWidget {
            background-color: #1e1e2e;
            color: #cdd6f4;
        }
        QLabel {
            color: #cdd6f4;
        }
        QStatusBar {
            background-color: #181825;
            color: #a6adc8;
            font-size: 11px;
        }
        QPushButton {
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover {
            background-color: #45475a;
            border-color: #89b4fa;
        }
        QPushButton:pressed {
            background-color: #585b70;
        }
        QPushButton:checked {
            background-color: #89b4fa;
            color: #1e1e2e;
            border-color: #89b4fa;
            font-weight: bold;
        }
    """)

    def _on_load_progression_from_library(self, filepath: str) -> None:
        """Called when the user clicks Load on an entry in the Saved tab.
        Pushes the progression into the chord_builder and switches to
        the Scale Finder tab so the user can see the result."""
        if self.chord_builder.load_progression_from_file(filepath):
            # Switch focus to the Scale Finder tab
            self.tabs.setCurrentWidget(self.chord_builder)

    def closeEvent(self, event):
        """Clean up on window close."""
        self.audio.shutdown()
        if self.daw is not None:
            self.daw.shutdown()
        event.accept()
