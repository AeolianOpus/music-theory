"""
Guitar fretboard visualization widget.
Shows chord shapes and scale patterns on a guitar neck.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from core.tuning import GUITAR_TUNINGS, Tuning


class FretboardWidget(QWidget):
    """Visual guitar fretboard showing notes, chords, and scales."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tuning = Tuning.from_preset("Standard (EADGBE)")
        self.num_frets = 15  # Show first 15 frets
        self.highlighted_notes: set[tuple[int, int]] = set()  # (string, fret) pairs
        self.note_colors: dict[tuple[int, int], QColor] = {}  # Custom colors per note
        self.show_note_names = True
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Fretboard display area - this takes up most of the space
        self.setMinimumHeight(400)
        self.setMinimumWidth(1000)
        
        # Add stretch to push controls to bottom
        layout.addStretch()
        
        # Tuning selector at bottom
        controls = QHBoxLayout()
        controls.setContentsMargins(10, 5, 10, 10)
        controls.addWidget(QLabel("Tuning:"))
        
        self.tuning_combo = QComboBox()
        from core.tuning import GUITAR_TUNINGS
        for tuning_name in GUITAR_TUNINGS.keys():
            self.tuning_combo.addItem(tuning_name, tuning_name)
        controls.addWidget(self.tuning_combo)
        controls.addStretch()
        
        layout.addLayout(controls)       
        
        
    def set_tuning(self, tuning: Tuning):
        """Change the guitar tuning."""
        self.tuning = tuning
        self.update()
        
    def highlight_notes(self, notes: set[tuple[int, int]], colors: dict[tuple[int, int], QColor] | None = None):
        """
        Highlight specific notes on the fretboard.
        notes: set of (string_index, fret_number) tuples
        colors: optional dict mapping (string, fret) to colors
        """
        self.highlighted_notes = notes
        self.note_colors = colors or {}
        self.update()
        
    def clear_highlights(self):
        """Remove all note highlights."""
        self.highlighted_notes.clear()
        self.note_colors.clear()
        self.update()
        
    def paintEvent(self, event):
        """Draw the fretboard using Yngwie's scalloped fretboard image."""
        print("paintEvent called!")
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        from PySide6.QtGui import QPixmap
        from pathlib import Path
        
        image_path = Path(__file__).parent / "fretboard_malmsteen.png"
        
        if image_path.exists():
            pixmap = QPixmap(str(image_path))
            
            # DON'T CROP - show the whole image for now
            # Scale to fit widget
            scaled = pixmap.scaled(
                self.width(), self.height() - 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Draw at top
            x = (self.width() - scaled.width()) // 2
            y = 10
            
            painter.drawPixmap(x, y, scaled)
            
            # Debug: print image dimensions
            print(f"Image size: {pixmap.width()} x {pixmap.height()}")
            
        else:
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                f"Image not found: {image_path}"
            )