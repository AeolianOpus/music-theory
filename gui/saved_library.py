"""
Saved-progression library index.

Each directory that the user has saved a progression into gets its own
`saved_index.json` file alongside the progression files themselves. This
module manages those per-directory indices and exposes a unified view
across them all.

Architecture:
  - QSettings stores the list of "known library directories"
  - Each known directory holds its own saved_index.json (JSON array of entries)
  - all_entries() walks every known directory, filters to entries whose
    files still exist on disk, and returns the merged list
  - Files moved or deleted outside the app silently disappear from the list

Index file format (saved_index.json in each directory):
  [
    {
      "filename": "Yngwie_HM_vamp.json",
      "name": "Yngwie HM vamp",
      "n_chords": 4,
      "saved_at": "2026-05-21T10:30:00"
    },
    ...
  ]

We store filename (not full path) inside each entry so the index travels
with the directory — moving a whole directory keeps it valid.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json
import os

from PySide6.QtCore import QSettings


INDEX_FILENAME = "saved_index.json"
SETTINGS_ORG = "MusicTheoryApp"
SETTINGS_APP = "ScaleFinder"
SETTINGS_KEY_DIRS = "known_library_dirs"


@dataclass
class SavedEntry:
    """One entry in the saved-progression library.
    `filepath` is the absolute path to the JSON progression file."""
    filepath: str
    name: str
    n_chords: int
    saved_at: str  # ISO format string

    @property
    def filename(self) -> str:
        return os.path.basename(self.filepath)

    @property
    def directory(self) -> str:
        return os.path.dirname(self.filepath)

    def saved_at_datetime(self) -> Optional[datetime]:
        """Parse saved_at to a datetime, or None if malformed."""
        try:
            return datetime.fromisoformat(self.saved_at)
        except (ValueError, TypeError):
            return None


# ── QSettings helpers ─────────────────────────────────────────────

def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def _known_dirs() -> list[str]:
    """Load the list of known library directories from QSettings.
    Returns a fresh list each call. Coerces to str (Pylance-friendly)."""
    raw = _settings().value(SETTINGS_KEY_DIRS, [])
    if isinstance(raw, list):
        return [d for d in raw if isinstance(d, str)]
    if isinstance(raw, str):
        # QSettings sometimes returns a single string instead of a list with one element
        return [raw] if raw else []
    return []


def _save_known_dirs(dirs: list[str]) -> None:
    """Persist the list of known library directories to QSettings."""
    _settings().setValue(SETTINGS_KEY_DIRS, dirs)


def _add_known_dir(directory: str) -> None:
    """Add a directory to the known-library set if not already present."""
    dirs = _known_dirs()
    if directory and directory not in dirs:
        dirs.append(directory)
        _save_known_dirs(dirs)


# ── Per-directory index file I/O ──────────────────────────────────

def _index_path(directory: str) -> str:
    return os.path.join(directory, INDEX_FILENAME)


def _load_index(directory: str) -> list[dict]:
    """Read saved_index.json from a directory. Returns [] if missing/corrupt."""
    path = _index_path(directory)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def _write_index(directory: str, entries: list[dict]) -> bool:
    """Write the per-directory index file. Returns False on I/O error."""
    path = _index_path(directory)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        return True
    except OSError:
        return False


# ── Public API ────────────────────────────────────────────────────

def register_save(filepath: str, name: str, n_chords: int) -> bool:
    """Record a saved progression in its directory's index.

    Called whenever the app saves OR loads a progression file, so that
    files loaded from previously-unseen locations get added to the library.

    Behavior:
      - Adds the file's directory to the known-library set (if new)
      - Updates the existing index entry (by filename) if one exists,
        else appends a new entry
      - Updates saved_at to "now"

    Returns False on I/O error writing the index, True otherwise.
    """
    directory = os.path.dirname(filepath)
    if not directory:
        return False

    filename = os.path.basename(filepath)
    entries = _load_index(directory)

    # Update existing entry or append new
    found = False
    for entry in entries:
        if entry.get("filename") == filename:
            entry["name"] = name
            entry["n_chords"] = n_chords
            entry["saved_at"] = datetime.now().isoformat(timespec="seconds")
            found = True
            break
    if not found:
        entries.append({
            "filename": filename,
            "name": name,
            "n_chords": n_chords,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })

    if not _write_index(directory, entries):
        return False

    _add_known_dir(directory)
    return True


def unregister(filepath: str) -> bool:
    """Remove an entry from the per-directory index by filename.
    Does NOT delete the file itself — caller is responsible for that.
    Returns True if an entry was removed."""
    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    entries = _load_index(directory)
    new_entries = [e for e in entries if e.get("filename") != filename]
    if len(new_entries) == len(entries):
        return False  # nothing to remove
    _write_index(directory, new_entries)
    return True


def rename(filepath: str, new_name: str) -> bool:
    """Change the display name of an entry. The on-disk filename is not
    affected. Returns True if the entry was found and renamed."""
    directory = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    entries = _load_index(directory)
    for entry in entries:
        if entry.get("filename") == filename:
            entry["name"] = new_name.strip() or entry.get("name", "Untitled")
            return _write_index(directory, entries)
    return False


def all_entries() -> list[SavedEntry]:
    """Return all entries across all known library directories.

    Filters out entries whose underlying file no longer exists. Also
    prunes known-library directories that no longer exist on disk
    (e.g., user deleted the whole folder).
    """
    dirs = _known_dirs()
    surviving_dirs: list[str] = []
    results: list[SavedEntry] = []

    for directory in dirs:
        if not os.path.isdir(directory):
            continue  # directory itself is gone; drop it from known list
        surviving_dirs.append(directory)
        for entry in _load_index(directory):
            filename = entry.get("filename")
            if not isinstance(filename, str):
                continue
            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue  # file moved/deleted outside the app
            name = entry.get("name", filename)
            n_chords = entry.get("n_chords", 0)
            saved_at = entry.get("saved_at", "")
            if not isinstance(name, str):
                name = str(name)
            if not isinstance(n_chords, int):
                try:
                    n_chords = int(n_chords)
                except (TypeError, ValueError):
                    n_chords = 0
            if not isinstance(saved_at, str):
                saved_at = ""
            results.append(SavedEntry(
                filepath=filepath,
                name=name,
                n_chords=n_chords,
                saved_at=saved_at,
            ))

    # Prune dropped directories from settings
    if len(surviving_dirs) != len(dirs):
        _save_known_dirs(surviving_dirs)

    return results