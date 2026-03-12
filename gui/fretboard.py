"""
Guitar fretboard visualization with procedural wood grain generation.
Uses Perlin noise to create realistic maple fretboard textures.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QLinearGradient
from pathlib import Path
from core.tuning import GUITAR_TUNINGS, Tuning


class FretboardWidget(QWidget):
    """Visual guitar fretboard with procedural wood grain."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tuning = Tuning.from_preset("Standard (EADGBE)")
        self.num_frets = 22
        self.highlighted_notes: set[tuple[int, int]] = set()
        self.note_colors: dict[tuple[int, int], QColor] = {}
        self.show_note_names = True
        
        # Fretboard display dimensions (set in paintEvent)
        self.fretboard_x = 0
        self.fretboard_y = 0
        self.fretboard_width = 0
        self.fretboard_height = 0
        
        # Procedural texture (generated once)
        self.wood_texture: QImage | None = None
        self._texture_generated = False
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tuning selector
        controls = QHBoxLayout()
        controls.setContentsMargins(20, 5, 20, 5)
        controls.addWidget(QLabel("Tuning:"))
        
        self.tuning_combo = QComboBox()
        for tuning_name in GUITAR_TUNINGS.keys():
            self.tuning_combo.addItem(tuning_name, tuning_name)
        self.tuning_combo.setMaximumWidth(200)
        controls.addWidget(self.tuning_combo)
        controls.addStretch()
        
        layout.addLayout(controls)
        layout.addStretch(1)
        
        self.setMinimumHeight(500)
        self.setMinimumWidth(1000)
        
        layout.addStretch(1)
    
        
    def paintEvent(self, event):
        """Draw the guitar with note overlays."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Catppuccin base background
        base_bg = QColor(30, 30, 46)
        painter.fillRect(self.rect(), base_bg)
        
        # Load guitar image
        image_path = Path(__file__).parent / "guitar_malmsteen.png"
        if not image_path.exists():
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Guitar image not found")
            return

        # Load image
        guitar_image = QImage(str(image_path))

        # Crop horizontally only - keep FULL original height
        crop_left = int(guitar_image.width() * 0.30)
        crop_width = int(guitar_image.width() * 0.70)

        # Use full height - no vertical cropping at all
        guitar_image = guitar_image.copy(crop_left, 0, crop_width, guitar_image.height())

        # Calculate scaling to fit widget while maintaining aspect ratio
        widget_ratio = self.width() / self.height()
        image_ratio = guitar_image.width() / guitar_image.height()

        if widget_ratio > image_ratio:
            # Widget is wider - fit to height
            scaled_height = self.height()
            scaled_width = int(scaled_height * image_ratio)
        else:
            # Widget is taller - fit to width
            scaled_width = self.width()
            scaled_height = int(scaled_width / image_ratio)

        # Center the image
        x_offset = (self.width() - scaled_width) // 2
        y_offset = (self.height() - scaled_height) // 2

        # Draw scaled guitar image
        scaled_image = guitar_image.scaled(
            scaled_width, 
            scaled_height, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        painter.drawImage(x_offset, y_offset, scaled_image)

        # Store dimensions for note overlay calculations
        self.guitar_x = x_offset
        self.guitar_y = y_offset
        self.guitar_width = scaled_width
        self.guitar_height = scaled_height

        # Calculate fret and string positions
        # Fretboard starts at ~35% from left, ends at ~95% from left
        fretboard_start_ratio = 0.35
        fretboard_end_ratio = 0.95

        # Strings are between ~40% and ~60% of height (center band)
        string_top_ratio = 0.40
        string_bottom_ratio = 0.60

        fretboard_pixel_start = int(scaled_width * fretboard_start_ratio)
        fretboard_pixel_end = int(scaled_width * fretboard_end_ratio)
        fretboard_pixel_width = fretboard_pixel_end - fretboard_pixel_start

        string_pixel_top = int(scaled_height * string_top_ratio)
        string_pixel_bottom = int(scaled_height * string_bottom_ratio)
        string_pixel_height = string_pixel_bottom - string_pixel_top

        # Calculate fret positions using equal temperament
        self.fret_positions = []
        for fret in range(self.num_frets + 1):
            if fret == 0:
                # Nut position
                fret_x = x_offset + fretboard_pixel_start
            else:
                # Equal temperament: distance = scale_length * (1 - 1/2^(fret/12))
                distance_ratio = 1 - (1 / (2 ** (fret / 12)))
                fret_x = x_offset + fretboard_pixel_start + int(fretboard_pixel_width * distance_ratio)

            self.fret_positions.append(fret_x)

        # Calculate string positions (6 strings evenly spaced)
        self.string_positions = []
        for string_idx in range(6):
            string_y = y_offset + string_pixel_top + int((string_pixel_height / 5) * string_idx)
            self.string_positions.append(string_y)

        # Draw note overlays
        self._draw_note_overlays(painter)


    def _draw_note_overlays(self, painter: QPainter):
        """Draw colored circles for highlighted notes."""
        if not self.highlighted_notes or not hasattr(self, 'fret_positions'):
            return

        for string_idx, fret_num in self.highlighted_notes:
            if fret_num >= len(self.fret_positions) - 1:
                continue

            if string_idx >= len(self.string_positions):
                continue

            # Calculate position
            if fret_num == 0:
                # Open string - place before nut
                note_x = self.fret_positions[0] - 15
            else:
                # Between frets
                note_x = (self.fret_positions[fret_num - 1] + self.fret_positions[fret_num]) / 2

            note_y = self.string_positions[string_idx]

            # Get color (default red for root, blue for others)
            color = self.note_colors.get((string_idx, fret_num), QColor(239, 68, 68))  # Catppuccin red

            # Draw circle
            painter.setPen(QPen(color.darker(120), 2))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(note_x, note_y), 12, 12)

            # Draw note name if enabled
            if self.show_note_names:
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                # TODO: Get actual note name from tuning + fret
                # painter.drawText(...)
    
    def _draw_strings(self, painter: QPainter, x: int, y: int, width: int, height: int):
        """Draw guitar strings."""
        num_strings = 6
        string_spacing = height / (num_strings + 1)
        
        # Catppuccin overlay color for strings
        string_color = QColor(108, 112, 134, 180)  # Semi-transparent
        
        for string_idx in range(num_strings):
            string_y = y + string_spacing * (string_idx + 1)
            
            # String thickness varies (thicker for lower strings)
            thickness = 1 + (string_idx * 0.3)
            painter.setPen(QPen(string_color, thickness))
            painter.drawLine(x, int(string_y), x + width, int(string_y))
    
    def _draw_frets(self, painter: QPainter, x: int, y: int, width: int, height: int):
        """Draw fret wires using equal temperament spacing."""
        # Calculate fret positions (12th root of 2 for equal temperament)
        scale_length = width * 0.92
        fret_positions = [x + 20]  # Nut position
        
        for fret in range(1, self.num_frets + 1):
            distance = scale_length * (1 - (1 / (2 ** (fret / 12))))
            fret_positions.append(int(x + 20 + distance))
        
        # Store for later use
        self.fret_positions = fret_positions
        
        # Catppuccin overlay for frets
        fret_color = QColor(88, 91, 112)
        
        for i, fret_x in enumerate(fret_positions):
            # Nut is thicker
            if i == 0:
                painter.setPen(QPen(fret_color.darker(120), 6))
            else:
                painter.setPen(QPen(fret_color, 3))
            
            painter.drawLine(fret_x, y, fret_x, y + height)
    
    def _draw_fret_markers(self, painter: QPainter, x: int, y: int, width: int, height: int):
        """Draw fret position markers (dots)."""
        marker_frets = [3, 5, 7, 9, 12, 15, 17, 19, 21]
        double_frets = [12]
        
        # Catppuccin text color for markers
        marker_color = QColor(205, 214, 244, 100)  # Semi-transparent
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(marker_color)
        
        for fret_num in marker_frets:
            if fret_num < len(self.fret_positions) - 1:
                # Position between frets
                center_x = (self.fret_positions[fret_num - 1] + self.fret_positions[fret_num]) / 2
                center_y = y + height / 2
                
                if fret_num in double_frets:
                    # Double dots for 12th fret
                    painter.drawEllipse(QPointF(center_x, center_y - height * 0.15), 8, 8)
                    painter.drawEllipse(QPointF(center_x, center_y + height * 0.15), 8, 8)
                else:
                    # Single dot
                    painter.drawEllipse(QPointF(center_x, center_y), 8, 8)
    
     
    def set_tuning(self, tuning: Tuning):
        """Change the guitar tuning."""
        self.tuning = tuning
        self.update()
    
    def highlight_notes(self, notes: set[tuple[int, int]], colors: dict[tuple[int, int], QColor] | None = None):
        """Highlight specific notes on the fretboard."""
        self.highlighted_notes = notes
        self.note_colors = colors or {}
        self.update()
    
    def clear_highlights(self):
        """Remove all note highlights."""
        self.highlighted_notes.clear()
        self.note_colors.clear()
        self.update()
    
    def regenerate_texture(self):
        """Generate a new unique wood grain pattern."""
        self._texture_generated = False
        self.update()