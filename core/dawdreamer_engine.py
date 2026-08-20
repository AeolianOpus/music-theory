"""
DawDreamer-based audio engine for professional VST instrument playback.
Pre-renders audio through VST plugins and streams to speakers via sounddevice.

This is an alternative backend to AudioEngine (FluidSynth). FluidSynth stays
for instant single-note play/arpeggio; DawDreamerEngine handles backing tracks
with studio-quality VST instruments.

Usage:
    engine = DawDreamerEngine()
    engine.initialize({"piano": "C:/path/to/piano.vst3"})
    audio = engine.render_chord(chord_notes=[60, 64, 67], duration_sec=2.0, instrument="piano")
    engine.stream_audio(audio)
    engine.shutdown()
"""
from __future__ import annotations

import threading
import time
from typing import Optional, Any

import numpy as np

import importlib.util
HAS_DAWDREAMER: bool = importlib.util.find_spec("dawdreamer") is not None

HAS_SOUNDDEVICE: bool = importlib.util.find_spec("sounddevice") is not None

# Default audio settings
SAMPLE_RATE = 44100
BUFFER_SIZE = 512


class DawDreamerEngine:
    """
    VST-based audio engine using DawDreamer for rendering and
    sounddevice for real-time streaming.
    """

    def __init__(self) -> None:
        self._engine: Any = None
        self._plugins: dict[str, Any] = {}  # name -> PluginProcessor
        self._vst_paths: dict[str, str] = {}  # name -> file path
        self._initialized: bool = False
        self._lock = threading.Lock()
        self._stream: Any = None  # sounddevice OutputStream
        self._stop_event = threading.Event()
        self._playback_thread: Optional[threading.Thread] = None

    def initialize(self, vst_paths: dict[str, str] | None = None) -> bool:
        """
        Initialize the DawDreamer render engine and load VST plugins.

        Args:
            vst_paths: dict mapping instrument names to VST3 file paths.
                       e.g. {"piano": "C:/Program Files/Common Files/VST3/MyPiano.vst3"}
        """
        if not HAS_DAWDREAMER:
            print("Warning: dawdreamer not installed. VST audio disabled.")
            return False

        if not HAS_SOUNDDEVICE:
            print("Warning: sounddevice not installed. Audio streaming disabled.")
            return False

        try:
            import dawdreamer
            _RenderEngine = getattr(dawdreamer, "RenderEngine")
            self._engine = _RenderEngine(
                sample_rate=SAMPLE_RATE,
                block_size=BUFFER_SIZE,
            )

            if vst_paths:
                self._vst_paths = vst_paths
                for name, path in vst_paths.items():
                    self._load_plugin(name, path)

            self._initialized = True
            return True

        except Exception as e:
            print(f"DawDreamer initialization error: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._engine is not None

    def _load_plugin(self, name: str, vst_path: str) -> bool:
        """Load a VST3 plugin and register it under a name."""
        if not self._engine:
            return False

        try:
            plugin = self._engine.make_plugin_processor(name, vst_path)
            if plugin is None:
                print(f"Failed to load VST: {name} from {vst_path}")
                return False

            self._plugins[name] = plugin
            print(f"Loaded VST: {name}")
            return True

        except Exception as e:
            print(f"Error loading VST '{name}': {e}")
            return False

    def list_plugins(self) -> list[str]:
        """Return names of all loaded plugins."""
        return list(self._plugins.keys())

    def get_plugin_parameters(self, name: str) -> list[dict[str, Any]]:
        """Return all parameters for a loaded plugin (useful for discovery)."""
        if name not in self._plugins:
            return []

        plugin = self._plugins[name]
        params = []
        for i in range(plugin.get_plugin_parameter_size()):
            params.append({
                "index": i,
                "name": plugin.get_plugin_parameter_name(i),
                "value": plugin.get_plugin_parameter(i),
            })
        return params

    def render_chord(
        self,
        chord_notes: list[int],
        duration_sec: float,
        instrument: str,
        velocity: int = 90,
        transpose: int = 0,
    ) -> np.ndarray:
        """
        Render a chord through a VST plugin.

        Args:
            chord_notes: list of MIDI note numbers (e.g. [60, 64, 67] for C major)
            duration_sec: how long to render in seconds
            instrument: name of the loaded plugin to use
            velocity: MIDI velocity (0-127)
            transpose: semitones to shift (e.g. -1 for Eb)

        Returns:
            numpy array of stereo audio (shape: [2, num_samples])
        """
        if not self.is_ready:
            return np.zeros((2, int(SAMPLE_RATE * duration_sec)))

        if instrument not in self._plugins:
            print(f"Plugin '{instrument}' not loaded.")
            return np.zeros((2, int(SAMPLE_RATE * duration_sec)))

        plugin = self._plugins[instrument]

        # Clear any previous MIDI
        plugin.clear_midi()

        # Schedule all notes: note_on at time 0, note_off near the end
        note_off_time = max(0.01, duration_sec - 0.05)
        for note in chord_notes:
            shifted = note + transpose
            if 0 <= shifted <= 127:
                plugin.add_midi_note(shifted, velocity, 0.0, note_off_time)

        # Build and render the graph
        graph = [
            (plugin, []),
        ]

        with self._lock:
            self._engine.load_graph(graph)
            self._engine.render(duration_sec)

        # Get rendered audio
        audio = self._engine.get_audio()
        return audio

    def render_sequence(
        self,
        chords: list[list[int]],
        durations: list[float],
        instrument: str,
        velocity: int = 90,
        transpose: int = 0,
    ) -> np.ndarray:
        """
        Render a sequence of chords as one continuous audio buffer.

        Args:
            chords: list of chord note lists
            durations: duration in seconds for each chord
            instrument: plugin name
            velocity: MIDI velocity
            transpose: semitone shift
        """
        buffers = []
        for notes, dur in zip(chords, durations):
            chunk = self.render_chord(notes, dur, instrument, velocity, transpose)
            buffers.append(chunk)

        if not buffers:
            return np.zeros((2, 0))

        return np.concatenate(buffers, axis=1)

    def stream_audio(self, audio: np.ndarray, blocking: bool = False) -> None:
        """
        Stream a pre-rendered audio buffer to speakers via sounddevice.

        Args:
            audio: stereo audio array, shape [2, num_samples]
            blocking: if True, blocks until playback finishes
        """
        if not HAS_SOUNDDEVICE:
            print("sounddevice not available.")
            return

        # sounddevice expects (samples, channels) layout
        interleaved = audio.T  # (num_samples, 2)

        self._stop_event.clear()

        import sounddevice as sd
        if blocking:
            sd.play(interleaved, samplerate=SAMPLE_RATE)
            sd.wait()
        else:
            self._playback_thread = threading.Thread(
                target=self._stream_worker,
                args=(interleaved,),
                daemon=True,
            )
            self._playback_thread.start()

    def _stream_worker(self, interleaved: np.ndarray) -> None:
        """Background worker that streams audio and watches for stop events."""
        import sounddevice as sd
        try:
            sd.play(interleaved, samplerate=SAMPLE_RATE)
            # Poll for stop event while playing
            frames = interleaved.shape[0]
            duration = frames / SAMPLE_RATE
            start = time.monotonic()
            while time.monotonic() - start < duration:
                if self._stop_event.is_set():
                    sd.stop()
                    return
                time.sleep(0.05)
            sd.wait()
        except Exception as e:
            print(f"Streaming error: {e}")

    def stop(self) -> None:
        """Stop any ongoing audio playback."""
        self._stop_event.set()
        if HAS_SOUNDDEVICE:
            import sounddevice as sd
            try:
                sd.stop()
            except Exception:
                pass

    def is_playing(self) -> bool:
        """Check if audio is currently streaming."""
        return (
            self._playback_thread is not None
            and self._playback_thread.is_alive()
        )

    def shutdown(self) -> None:
        """Clean up all resources."""
        self.stop()
        self._plugins.clear()
        self._engine = None
        self._initialized = False
