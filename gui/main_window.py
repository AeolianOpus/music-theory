from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QStatusBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from core.audio_engine import AudioEngine
from gui.chord_builder import ChordBuilder


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, audio_engine: AudioEngine, base_dir: str, parent=None):
        super().__init__(parent)
        self.audio = audio_engine
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
        self.chord_builder = ChordBuilder(self.audio)
        self.tabs.addTab(self.chord_builder, "🎵 Scale Finder")

        from gui.fretboard import FretboardWidget

        # Add fretboard
        self.fretboard = FretboardWidget()
        self.tabs.addTab(self.fretboard, "Guitar")

        # Connect scale selection to fretboard
        self.chord_builder.scale_selected.connect(self._update_fretboard_from_scale)

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

        self.tabs.addTab(self._placeholder("Saved Progressions",
            "View and manage saved chord progressions and scale choices."),
            "💾 Saved")

        layout.addWidget(self.tabs)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        audio_status = "🔊 Audio ready" if self.audio.is_ready else "🔇 No SoundFont loaded"
        self.status.showMessage(audio_status)

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

    def _update_fretboard_from_scale(self, scale_match):
        """Update fretboard visualization when a scale is selected."""
        # Extract scale notes from the match
        scale_notes = scale_match.scale.notes

        # TODO: Calculate fret positions for each note across all strings
        # For now, just log it
        print(f"Scale selected: {scale_match.scale.name} - Notes: {scale_notes}")

        # You'll need to implement the logic to map notes to (string, fret) positions
        # based on the current tuning, then call:
        # self.fretboard.highlight_notes(positions, colors)
    
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

    def closeEvent(self, event):
        """Clean up on window close."""
        self.audio.shutdown()
        event.accept()
