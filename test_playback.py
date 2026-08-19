"""
Interactive playback test GUI. Run from project root: python test_playback.py
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QLineEdit, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.music_theory import ChordProgression
from core.audio_engine import AudioEngine
from core.playback import PlaybackEngine, STYLE_PRESETS, DEFAULT_SOUNDFONT, INSTRUMENT_SOURCES

SOUNDFONTS: dict[str, str] = {
    "compifont":      "soundfonts/Compifont.sf2",
    "musyng":         "soundfonts/Musyng_Kite.sf2",
    "tyroland":       "soundfonts/TyrolandGS27fixed.sf2",
    "timbres":        "soundfonts/Timbres_of_Heaven_(XGM)_4.00(G).sf2",
    "hq_orch":        "soundfonts/HQ_Orchestral_Soundfont_Collection.sf2",
    "fluidr3":        "soundfonts/FluidR3_GM_GS.sf2",
    "guitar_metal":   "soundfonts/Guitar_for_Metal_GM.sf2",
    "drums_hardrock": "soundfonts/Drums_HardRockDrumsV3.sf2",
}

PRIMARY_SF = "compifont"

THEME = """
    QWidget { background-color: #1e1e2e; color: #cdd6f4; }
    QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 8px; padding-top: 14px; }
    QGroupBox::title { color: #f5c2e7; subcontrol-position: top left; padding: 2px 8px; }
    QPushButton {
        background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
        border-radius: 6px; padding: 8px 16px; font-size: 12px;
    }
    QPushButton:hover { background-color: #45475a; border-color: #89b4fa; }
    QPushButton:pressed { background-color: #585b70; }
    QPushButton#play_btn { background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; }
    QPushButton#play_btn:hover { background-color: #94e2d5; }
    QPushButton#stop_btn { background-color: #f38ba8; color: #1e1e2e; font-weight: bold; }
    QPushButton#stop_btn:hover { background-color: #eba0ac; }
    QComboBox {
        background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
        border-radius: 4px; padding: 4px 8px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView { background-color: #313244; color: #cdd6f4; selection-background-color: #45475a; }
    QSpinBox {
        background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
        border-radius: 4px; padding: 4px 8px;
    }
    QLineEdit {
        background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
        border-radius: 4px; padding: 6px 10px; font-size: 13px;
    }
    QLabel { background: transparent; }
    QLabel#status { color: #a6adc8; font-size: 11px; }
    QLabel#title { color: #f5c2e7; font-size: 18px; font-weight: bold; }
"""


class PlaybackTestWindow(QWidget):
    def __init__(self, audio: AudioEngine):
        super().__init__()
        self.audio = audio
        self.playback = PlaybackEngine(audio)
        self.setWindowTitle("Playback Test")
        self.setFixedSize(520, 340)
        self.setStyleSheet(THEME)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Playback Test")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Chords input
        chord_row = QHBoxLayout()
        chord_row.addWidget(QLabel("Chords:"))
        self.chord_input = QLineEdit("Am G F E")
        self.chord_input.setPlaceholderText("Am G F E7")
        chord_row.addWidget(self.chord_input)
        layout.addLayout(chord_row)

        # Style + Tempo + Transpose
        settings_row = QHBoxLayout()

        settings_row.addWidget(QLabel("Style:"))
        self.style_combo = QComboBox()
        for name in STYLE_PRESETS:
            self.style_combo.addItem(name.replace("_", " ").title(), name)
        self.style_combo.setCurrentIndex(list(STYLE_PRESETS.keys()).index("neoclassical_metal"))
        settings_row.addWidget(self.style_combo)

        settings_row.addWidget(QLabel("BPM:"))
        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(40, 240)
        self.tempo_spin.setValue(110)
        self.tempo_spin.valueChanged.connect(self._on_tempo_changed)
        settings_row.addWidget(self.tempo_spin)

        settings_row.addWidget(QLabel("Transpose:"))
        self.transpose_spin = QSpinBox()
        self.transpose_spin.setRange(-12, 12)
        self.transpose_spin.setValue(-1)
        settings_row.addWidget(self.transpose_spin)

        layout.addLayout(settings_row)

        sf_row = QHBoxLayout()
        sf_row.addWidget(QLabel("SoundFont:"))
        self.sf_combo = QComboBox()
        for name in SOUNDFONTS:
            self.sf_combo.addItem(name)
        self.sf_combo.setCurrentText(PRIMARY_SF)
        sf_row.addWidget(self.sf_combo)
        sf_row.addStretch()
        layout.addLayout(sf_row)

        # Play / Stop
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setObjectName("play_btn")
        self.play_btn.setFixedHeight(44)
        self.play_btn.clicked.connect(self._play)
        btn_row.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("stop_btn")
        self.stop_btn.setFixedHeight(44)
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        layout.addLayout(btn_row)

        # Status
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _play(self):
        text = self.chord_input.text().strip()
        if not text:
            return
        try:
            chords = text.replace(",", " ").replace("-", " ").split()
            prog = ChordProgression.parse(chords)
        except ValueError as e:
            self.status_label.setText(f"Error: {e}")
            return

        style = self.style_combo.currentData()
        tempo = self.tempo_spin.value()
        transpose = self.transpose_spin.value()

        sf_name = self.sf_combo.currentText()
        for inst in ["chord", "bass", "pad", "choir", "drone"]:
            preset = STYLE_PRESETS.get(style, {})
            inst_name = preset.get(f"{inst}_instrument")
            if inst_name:
                INSTRUMENT_SOURCES[inst_name] = sf_name
        self.playback.play_progression(
            prog, tempo=tempo, style=style,
            loop=True, transpose=transpose,
        )
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(
            f"Playing: {' - '.join(c.display_name for c in prog.chords)} | "
            f"{style} | {tempo} BPM | transpose={transpose}"
        )

    def _stop(self):
        self.playback.stop()
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Stopped")

    def _on_tempo_changed(self, bpm):
        if self.playback.is_playing():
            self.playback.set_tempo(bpm)

    def closeEvent(self, event):
        self.playback.stop()
        self.audio.shutdown()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    audio = AudioEngine()
    primary_path = SOUNDFONTS[PRIMARY_SF]
    if not audio.initialize(primary_path, soundfont_name=PRIMARY_SF):
        print(f"Failed to initialize audio with {PRIMARY_SF}")
        sys.exit(1)
    print(f"Loaded: {PRIMARY_SF}")

    for name, path in SOUNDFONTS.items():
        if name == PRIMARY_SF:
            continue
        if audio.load_soundfont(name, path):
            print(f"Loaded: {name}")

    window = PlaybackTestWindow(audio)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()