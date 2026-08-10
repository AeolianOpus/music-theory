"""
Saved Progressions tab — library view of all saved chord progressions.

Reads from gui.saved_library.all_entries() to get the unified list across
all known library directories. Each entry can be expanded to reveal
Load / Rename / Delete actions.

The widget refreshes automatically when it becomes visible (e.g., when
the user switches to the Saved tab), so newly-saved progressions appear
without an explicit refresh.
"""

from __future__ import annotations
from typing import Optional
from datetime import datetime
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QSizePolicy, QMessageBox, QInputDialog, QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QEvent

from gui.saved_library import all_entries, unregister, rename, SavedEntry


class _EntryRow(QFrame):
    """A single saved-progression row. Collapsed by default, expandable
    to show the filepath and Load / Rename / Delete buttons."""

    load_requested = Signal(str)      # emits filepath
    delete_requested = Signal(str)    # emits filepath
    rename_requested = Signal(str)    # emits filepath

    def __init__(self, entry: SavedEntry, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.entry = entry
        self.expanded = False
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            _EntryRow {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
            _EntryRow:hover {
                border-color: #89b4fa;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # ── Header row (always visible, click to toggle expand) ──
        header = QHBoxLayout()
        header.setSpacing(10)

        self.expand_indicator = QLabel("▸")
        self.expand_indicator.setStyleSheet(
            "color: #a6adc8; font-size: 11pt; background: transparent;"
        )
        self.expand_indicator.setFixedWidth(14)
        header.addWidget(self.expand_indicator)

        self.name_label = QLabel(entry.name)
        self.name_label.setStyleSheet(
            "color: #cdd6f4; font-size: 13pt; font-weight: bold; background: transparent;"
        )
        header.addWidget(self.name_label)

        header.addStretch()

        meta = self._format_meta(entry)
        self.meta_label = QLabel(meta)
        self.meta_label.setStyleSheet(
            "color: #a6adc8; font-size: 10pt; background: transparent;"
        )
        header.addWidget(self.meta_label)

        outer.addLayout(header)

        # ── Expanded section (hidden by default) ──
        self.details_widget = QWidget()
        details = QVBoxLayout(self.details_widget)
        details.setContentsMargins(20, 4, 0, 0)
        details.setSpacing(6)

        self.path_label = QLabel(f"Location: {entry.directory}")
        self.path_label.setStyleSheet(
            "color: #6c7086; font-size: 9pt; background: transparent;"
        )
        self.path_label.setWordWrap(True)
        details.addWidget(self.path_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.load_btn = QPushButton("📂 Load")
        self.load_btn.setFixedHeight(32)
        self.load_btn.setMinimumWidth(80)
        self.load_btn.clicked.connect(self._on_load)
        actions.addWidget(self.load_btn)

        self.rename_btn = QPushButton("✏️ Rename")
        self.rename_btn.setFixedHeight(32)
        self.rename_btn.setMinimumWidth(80)
        self.rename_btn.clicked.connect(self._on_rename)
        actions.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setFixedHeight(32)
        self.delete_btn.setMinimumWidth(80)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                color: #f38ba8;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #f38ba8;
            }
        """)
        self.delete_btn.clicked.connect(self._on_delete)
        actions.addWidget(self.delete_btn)

        actions.addStretch()
        details.addLayout(actions)

        self.details_widget.setVisible(False)
        outer.addWidget(self.details_widget)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _format_meta(self, entry: SavedEntry) -> str:
        """Compact metadata string shown on the right of the collapsed row."""
        chord_part = f"{entry.n_chords} chords" if entry.n_chords != 1 else "1 chord"
        dt = entry.saved_at_datetime()
        if dt is not None:
            date_part = dt.strftime("%Y-%m-%d %H:%M")
            return f"{chord_part}  ·  {date_part}"
        return chord_part

    def mousePressEvent(self, event) -> None:
        """Click anywhere on the row header to toggle expansion.
        Clicks on the action buttons themselves don't reach here (they
        consume the event), so this is purely the header tap behavior."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_expanded()
        super().mousePressEvent(event)

    def _toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self.details_widget.setVisible(self.expanded)
        self.expand_indicator.setText("▾" if self.expanded else "▸")

    def _on_load(self) -> None:
        self.load_requested.emit(self.entry.filepath)

    def _on_delete(self) -> None:
        self.delete_requested.emit(self.entry.filepath)

    def _on_rename(self) -> None:
        self.rename_requested.emit(self.entry.filepath)


class SavedProgressionsTab(QWidget):
    """Top-level Saved tab widget. Maintains the list of saved-entry rows,
    handles sort toggling, refresh, and per-row actions.

    Emits load_progression_requested(filepath) when the user clicks Load
    on a row — the main window wires this to chord_builder.load_progression_from_file()
    and switches to the Scale Finder tab.
    """

    load_progression_requested = Signal(str)  # emits filepath

    SORT_RECENT = "recent"
    SORT_ALPHA = "alpha"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.sort_mode = self.SORT_RECENT  # default
        self._entry_rows: list[_EntryRow] = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Header ──
        header = QHBoxLayout()
        title = QLabel("Saved Progressions")
        title.setStyleSheet(
            "color: #cdd6f4; font-size: 18pt; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch()

        # Sort toggle buttons
        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet("color: #a6adc8; font-size: 11pt;")
        header.addWidget(sort_label)

        self.sort_group = QButtonGroup(self)
        self.sort_group.setExclusive(True)

        self.sort_recent_btn = QPushButton("Recent")
        self.sort_recent_btn.setCheckable(True)
        self.sort_recent_btn.setChecked(True)
        self.sort_recent_btn.setFixedHeight(32)
        self.sort_recent_btn.setMinimumWidth(80)
        self.sort_group.addButton(self.sort_recent_btn)
        header.addWidget(self.sort_recent_btn)

        self.sort_alpha_btn = QPushButton("A–Z")
        self.sort_alpha_btn.setCheckable(True)
        self.sort_alpha_btn.setFixedHeight(32)
        self.sort_alpha_btn.setMinimumWidth(80)
        self.sort_group.addButton(self.sort_alpha_btn)
        header.addWidget(self.sort_alpha_btn)

        self.sort_recent_btn.clicked.connect(lambda: self._set_sort(self.SORT_RECENT))
        self.sort_alpha_btn.clicked.connect(lambda: self._set_sort(self.SORT_ALPHA))

        # Refresh button
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setFixedHeight(32)
        self.refresh_btn.setMinimumWidth(90)
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        # ── Scrollable list ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty-state placeholder (shown when no entries)
        self.empty_label = QLabel(
            "No saved progressions yet.\n\n"
            "Build a progression in the Scale Finder tab, then click Save."
        )
        self.empty_label.setStyleSheet(
            "color: #6c7086; font-style: italic; font-size: 12pt; padding: 40px;"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scroll_area.setWidget(self.list_container)

    def showEvent(self, event) -> None:
        """Refresh whenever the tab becomes visible — this catches saves
        that happened while the user was on another tab."""
        super().showEvent(event)
        self.refresh()

    def _set_sort(self, mode: str) -> None:
        self.sort_mode = mode
        self._rerender()

    def refresh(self) -> None:
        """Reload entries from the library and rerender."""
        self._rerender()

    def _rerender(self) -> None:
        """Clear and rebuild the entry rows from the current library state."""
        # Clear existing rows from the layout
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None and widget is not self.empty_label:
                widget.setParent(None)
                widget.deleteLater()
        self._entry_rows.clear()

        # Load and sort entries
        entries = all_entries()
        entries = self._sort_entries(entries)

        if not entries:
            self.list_layout.addWidget(self.empty_label)
            self.empty_label.setVisible(True)
            return

        self.empty_label.setVisible(False)

        for entry in entries:
            row = _EntryRow(entry)
            row.load_requested.connect(self._on_load)
            row.delete_requested.connect(self._on_delete)
            row.rename_requested.connect(self._on_rename)
            self.list_layout.addWidget(row)
            self._entry_rows.append(row)

    def _sort_entries(self, entries: list[SavedEntry]) -> list[SavedEntry]:
        if self.sort_mode == self.SORT_ALPHA:
            return sorted(entries, key=lambda e: e.name.lower())
        # SORT_RECENT — newest first; entries with unparseable dates go last
        def sort_key(e: SavedEntry):
            dt = e.saved_at_datetime()
            # Sort by date desc; use min datetime as fallback for unparseable
            return (dt is None, -(dt.timestamp() if dt else 0))
        return sorted(entries, key=sort_key)

    def _on_load(self, filepath: str) -> None:
        """User clicked Load on a row — propagate to main window."""
        self.load_progression_requested.emit(filepath)

    def _on_delete(self, filepath: str) -> None:
        """User clicked Delete on a row — confirm, delete file + index entry, refresh."""
        filename = os.path.basename(filepath)
        reply = QMessageBox.question(
            self,
            "Delete progression?",
            f"Delete '{filename}'?\n\nThis will permanently delete the file "
            f"from disk. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Delete the file from disk first
        if os.path.isfile(filepath):
            try:
                os.remove(filepath)
            except OSError as exc:
                QMessageBox.critical(
                    self, "Delete failed",
                    f"Could not delete {filepath}:\n{exc}",
                )
                return

        # Remove from index
        unregister(filepath)
        self.refresh()

    def _on_rename(self, filepath: str) -> None:
        """User clicked Rename on a row — prompt for new name, update index."""
        # Find current name from the row's entry
        current_name = ""
        for row in self._entry_rows:
            if row.entry.filepath == filepath:
                current_name = row.entry.name
                break

        new_name, ok = QInputDialog.getText(
            self, "Rename Progression",
            "New name:",
            text=current_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return

        if not rename(filepath, new_name):
            QMessageBox.warning(
                self, "Rename failed",
                "Could not update the library index.",
            )
            return

        self.refresh()