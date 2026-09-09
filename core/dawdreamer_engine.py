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

import contextlib
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any

import numpy as np

import importlib.util
HAS_DAWDREAMER: bool = importlib.util.find_spec("dawdreamer") is not None

HAS_SOUNDDEVICE: bool = importlib.util.find_spec("sounddevice") is not None


@contextlib.contextmanager
def _silence_native_output():
    """Redirect OS-level stdout (fd 1) AND stderr (fd 2) to devnull for the
    duration of the context. Kontakt writes its noisy startup messages
    (PresetSlotManager, cannot resolve resource, nil, [error] lines) to
    fd 1, not fd 2, so we swap both. Python's sys.stdout/sys.stderr
    redirection doesn't reach fd 1/2 — we have to dup2 at the OS level.
    Restores both fds on exit even on exception.

    Callers must NOT print() from Python inside the block — those go to
    fd 1 too and will be swallowed. Do prints before or after.
    """
    # Flush anything Python has buffered so we don't lose it
    sys.stdout.flush()
    sys.stderr.flush()
    saved_out = os.dup(1)
    saved_err = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        os.close(devnull_fd)
        os.close(saved_out)
        os.close(saved_err)

# Default audio settings
SAMPLE_RATE = 44100
BUFFER_SIZE = 512

KONTAKT_VST3 = r"C:\Program Files\Common Files\VST3\Kontakt 8.vst3"

DEFAULT_PRESETS = {
    "piano": "presets/kontakt_piano_uno.bin",
    "bass": "presets/kontakt_classic_bass.bin",
    "strings": "presets/kontakt_strings.bin",
    "pad": "presets/kontakt_pad.bin",
    "drums": "presets/kontakt_drums.bin",
    "rock_guitar": "presets/kontakt_rock_guitar.bin",
    "choir": "presets/kontakt_choir.bin",
}


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
        # Listeners notified whenever is_ready transitions (e.g. GUI status
        # bar). Called from whichever thread flips readiness — Qt listeners
        # must marshal to the main thread themselves (use a queued signal).
        self._ready_listeners: list = []

    def initialize(self, vst_paths: dict[str, str] | None = None) -> bool:
        """
        Initialize the DawDreamer render engine and load VST plugins.

        Args:
            vst_paths: dict mapping instrument names to VST3 file paths.
                       e.g. {"piano": "C:/Program Files/Common Files/VST3/MyPiano.vst3"}

        Notifies any registered ready-listeners once readiness settles
        (success OR failure — listeners get the final state either way).
        """
        if not HAS_DAWDREAMER:
            print("Warning: dawdreamer not installed. VST audio disabled.")
            self._notify_ready_listeners()
            return False

        if not HAS_SOUNDDEVICE:
            print("Warning: sounddevice not installed. Audio streaming disabled.")
            self._notify_ready_listeners()
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

            # Load presets BEFORE flipping _initialized. is_ready reads
            # from _initialized, and callers may check is_ready to decide
            # whether to route playback to VST. If we flip early, they get
            # a "ready" engine with no plugins loaded yet.
            self.load_presets()
            self._initialized = True
            self._notify_ready_listeners()
            return True

        except Exception as e:
            print(f"DawDreamer initialization error: {e}")
            self._notify_ready_listeners()
            return False

    def add_ready_listener(self, callback) -> None:
        """Register a callback to fire when readiness changes. Called with
        no arguments; the listener is expected to check is_ready itself.
        Fires once at end of initialize() (success or failure)."""
        self._ready_listeners.append(callback)

    def _notify_ready_listeners(self) -> None:
        """Call every registered ready-listener. Swallows per-listener
        exceptions so one bad listener can't break the others or the
        initialize() flow."""
        for cb in self._ready_listeners:
            try:
                cb()
            except Exception as e:
                print(f"ready listener {cb!r} raised: {e}")

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

    def load_presets(
        self,
        presets: dict[str, str] | None = None,
        parallel: bool = False,
        max_workers: int | None = None,
    ) -> None:
        """Load Kontakt instances with saved state files.

        Args:
            presets: dict mapping role names to .bin state file paths.
                 Uses DEFAULT_PRESETS if not provided.
            parallel: if True, load presets concurrently across a thread
                pool. Defaults to False because Kontakt 8 hangs on
                concurrent instantiation on Windows (tested 2026-08-26).
                Parallel machinery is kept for future VST types that
                tolerate it; do not enable for Kontakt.
            max_workers: worker count for parallel mode. Default is min(len,
                 os.cpu_count()) — one thread per preset, capped at CPU count
                 to avoid disk contention on the sample library reads.

        Note: Kontakt writes cosmetic errors ("PresetSlotManager::selectSlot",
        "cannot resolve resource: resources_ENG", stray "nil" lines) directly
        to OS-level stderr (fd 2) during load_state(). These are harmless in
        a headless render context. We redirect fd 2 only around
        plugin.load_state() so errors from make_plugin_processor() still
        surface. In parallel mode the silence still applies, but note that
        it's process-wide during the parallel window — real stderr writes
        from unrelated code (unlikely at startup) would also be suppressed.
        """
        if self._engine is None:
            return

        preset_map = presets or DEFAULT_PRESETS

        if not parallel:
            # Sequential path — original behavior, kept as fallback.
            for name, state_path in preset_map.items():
                self._load_single_preset(name, state_path)
            return

        # Parallel path — load presets concurrently.
        # We wrap the entire parallel section in the stderr silencer
        # because fd 2 is process-wide; toggling it inside each worker
        # would race between threads.
        worker_count = max_workers or min(len(preset_map), os.cpu_count() or 4)
        with _silence_native_output():
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                # Submit all preset loads; each returns (name, plugin_or_None)
                futures = {
                    pool.submit(self._load_preset_worker, name, state_path): name
                    for name, state_path in preset_map.items()
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        result_name, plugin = future.result()
                        if plugin is not None:
                            self._plugins[result_name] = plugin
                            # print outside silence block via stderr won't
                            # reach the terminal, so route to real stdout
                            # which is untouched by _silence_native_stderr
                            print(f"Loaded preset: {result_name}", flush=True)
                        else:
                            print(f"Failed to load preset: {name}", flush=True)
                    except Exception as e:
                        print(f"Preset '{name}' raised: {type(e).__name__}: {e}",
                              flush=True)

    def _load_single_preset(self, name: str, state_path: str) -> None:
        """Sequential-path helper: create + load-state + register, with the
        stderr silence wrapped around just load_state (fine when serial)."""
        plugin = self._engine.make_plugin_processor(name, KONTAKT_VST3)
        if plugin is None:
            print(f"Failed to create Kontakt instance for '{name}'")
            return
        with _silence_native_output():
            plugin.load_state(state_path)
        self._plugins[name] = plugin
        print(f"Loaded preset: {name}")

    def _load_preset_worker(
        self, name: str, state_path: str
    ) -> tuple[str, Any]:
        """Parallel-path worker: create + load-state and return the plugin
        (or None on failure). Registration into self._plugins happens back
        on the main thread in load_presets() to avoid dict-mutation races.
        stderr silencing is applied by the caller, wrapping all workers."""
        plugin = self._engine.make_plugin_processor(name, KONTAKT_VST3)
        if plugin is None:
            return (name, None)
        plugin.load_state(state_path)
        return (name, plugin)
    
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

    def render_chord_layered(
        self,
        chord_notes: list[int],
        bass_note: int,
        duration_sec: float,
        layers: dict[str, int],
        transpose: int = 0,
    ) -> np.ndarray:
        """
        Render a chord through multiple instrument layers and mix.

        Args:
            chord_notes: MIDI notes for chord voicing (e.g. [60, 64, 67])
            bass_note: single MIDI note for bass
            duration_sec: render duration in seconds
            layers: dict of preset_name -> velocity for each active layer
                    e.g. {"piano": 90, "bass": 100, "strings": 70}
            transpose: semitone shift

        Returns:
            stereo audio array, shape [2, num_samples]
        """
        num_samples = int(SAMPLE_RATE * duration_sec)
        mixed = np.zeros((2, num_samples), dtype=np.float32)

        for preset_name, velocity in layers.items():
            if preset_name not in self._plugins:
                continue

            plugin = self._plugins[preset_name]
            plugin.clear_midi()

            note_off_time = max(0.01, duration_sec - 0.05)

            if preset_name == "bass":
                shifted = bass_note + transpose
                if 0 <= shifted <= 127:
                    plugin.add_midi_note(shifted, velocity, 0.0, note_off_time)
            elif preset_name == "drums":
                beats = max(1, int(duration_sec * 2))
                beat_dur = duration_sec / beats
                for b in range(beats):
                    plugin.add_midi_note(36, velocity, b * beat_dur, min(b * beat_dur + 0.1, duration_sec))
            else:
                for note in chord_notes:
                    shifted = note + transpose
                    if 0 <= shifted <= 127:
                        plugin.add_midi_note(shifted, velocity, 0.0, note_off_time)

            with self._lock:
                self._engine.load_graph([(plugin, [])])
                self._engine.render(duration_sec)

            audio = self._engine.get_audio()
            stereo = audio[:2]
            if stereo.shape[1] >= num_samples:
                mixed += stereo[:, :num_samples]
            else:
                mixed[:, :stereo.shape[1]] += stereo

        peak = np.abs(mixed).max()
        if peak > 0.95:
            mixed = mixed * (0.9 / peak)

        return mixed
    
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
