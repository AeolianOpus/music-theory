"""
Guitar fretboard visualization with procedural wood grain generation.
Uses Perlin noise to create realistic maple fretboard textures.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QImage, QPixmap, QLinearGradient
from pathlib import Path
from core.tuning import GUITAR_TUNINGS, Tuning
from noise import pnoise2
import random


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
    
    def _sample_malmsteen_palette(self) -> list[QColor]:
        """Extract color palette from the Malmsteen fretboard image."""
        image_path = Path(__file__).parent / "fretboard_malmsteen.png"
        
        if not image_path.exists():
            # Fallback: Realistic maple colors
            return [
                QColor(245, 222, 179),  # Light maple (wheat)
                QColor(222, 184, 135),  # Medium maple (burlywood)
                QColor(205, 133, 63),   # Dark grain (peru)
                QColor(160, 82, 45),    # Darker grain (sienna)
                QColor(210, 180, 140),  # Tan variation
            ]
        
        # Sample colors from the actual image
        image = QImage(str(image_path))
        colors = []
        
        # Sample from multiple points
        sample_points = [
            (image.width() // 4, image.height() // 2),
            (image.width() // 2, image.height() // 3),
            (image.width() // 2, 2 * image.height() // 3),
            (3 * image.width() // 4, image.height() // 2),
        ]
        
        for x, y in sample_points:
            if 0 <= x < image.width() and 0 <= y < image.height():
                colors.append(image.pixelColor(x, y))
        
        if colors:
            return colors
        else:
            # Fallback to default palette
            return [
                QColor(245, 222, 179),
                QColor(222, 184, 135),
                QColor(205, 133, 63),
                QColor(160, 82, 45),
                QColor(210, 180, 140),
            ]
    
    def _generate_wood_texture(self, width: int, height: int) -> QImage:
        """Generate realistic wood grain using Perlin noise."""
        # Get maple color palette
        palette = self._sample_malmsteen_palette()
        
        # Catppuccin peach tint for theming
        theme_tint = QColor(250, 179, 135)
        
        # Random seed for variation
        seed = random.randint(1, 10000)
        
        # Create texture
        texture = QImage(width, height, QImage.Format.Format_RGB32)
        
        for y in range(height):
            for x in range(width):
                # Generate wood grain using pnoise2 (emphasize horizontal flow)
                noise_val = (
                    0.5 * pnoise2(x / width * 2 + seed, y / height * 0.5, octaves=3) +
                    0.3 * pnoise2(x / width * 4 + seed, y / height * 1.0, octaves=6) +
                    0.2 * pnoise2(x / width * 8 + seed, y / height * 2.0, octaves=10)
                )
                
                # Map noise to color palette
                noise_normalized = (noise_val + 1) / 2  # -1..1 → 0..1
                color_index = int(noise_normalized * (len(palette) - 1))
                color_index = max(0, min(len(palette) - 1, color_index))
                
                base_color = palette[color_index]
                
                # Apply subtle theme tint (10% blend)
                r = int(0.9 * base_color.red() + 0.1 * theme_tint.red())
                g = int(0.9 * base_color.green() + 0.1 * theme_tint.green())
                b = int(0.9 * base_color.blue() + 0.1 * theme_tint.blue())
                
                # Slight darkening for theme integration
                r = int(r * 0.85)
                g = int(g * 0.85)
                b = int(b * 0.85)
                
                texture.setPixelColor(x, y, QColor(r, g, b))
        
        return texture
    
    def paintEvent(self, event):
        """Draw the procedural fretboard."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Catppuccin base background
        base_bg = QColor(30, 30, 46)
        painter.fillRect(self.rect(), base_bg)
        
        # Calculate fretboard dimensions (centered, 70% height)
        padding = 60
        fb_height = int(self.height() * 0.7)
        fb_width = self.width() - padding * 2
        fb_x = padding
        fb_y = (self.height() - fb_height) // 2
        
        # Store for note overlays later
        self.fretboard_x = fb_x
        self.fretboard_y = fb_y
        self.fretboard_width = fb_width
        self.fretboard_height = fb_height
        
        # Generate wood texture once
        if not self._texture_generated:
            self.wood_texture = self._generate_wood_texture(fb_width, fb_height)
            self._texture_generated = True
        
        # Draw wood texture
        if self.wood_texture:
            painter.drawImage(fb_x, fb_y, self.wood_texture)
        
        # Draw fretboard elements
        self._draw_strings(painter, fb_x, fb_y, fb_width, fb_height)
        self._draw_frets(painter, fb_x, fb_y, fb_width, fb_height)
        self._draw_fret_markers(painter, fb_x, fb_y, fb_width, fb_height)
        
        # Draw note overlays if any
        self._draw_note_overlays(painter)
    
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
    
    def _draw_note_overlays(self, painter: QPainter):
        """Draw colored circles for highlighted notes."""
        if not self.highlighted_notes or not hasattr(self, 'fret_positions'):
            return
        
        num_strings = 6
        string_spacing = self.fretboard_height / (num_strings + 1)
        
        for string_idx, fret_num in self.highlighted_notes:
            if fret_num >= len(self.fret_positions) - 1:
                continue
            
            # Calculate position
            if fret_num == 0:
                # Open string (at nut)
                note_x = self.fret_positions[0] - 15
            else:
                # Between frets
                note_x = (self.fret_positions[fret_num - 1] + self.fret_positions[fret_num]) / 2
            
            note_y = self.fretboard_y + string_spacing * (string_idx + 1)
            
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