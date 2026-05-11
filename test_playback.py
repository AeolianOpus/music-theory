"""
Manual playback test. Run from project root: python test_playback.py
Plays a few progressions across different style presets.
Press Ctrl+C to stop early.

Loads multiple soundfonts so playback.py can route specific instruments to
specific SF2s via INSTRUMENT_SOURCES. With INSTRUMENT_SOURCES empty (default),
every instrument resolves to DEFAULT_SOUNDFONT (compifont) — this run is the
"all routed through compifont" baseline. Fill in INSTRUMENT_SOURCES later
once you've heard what's weak.
"""
import time
from core.music_theory import ChordProgression
from core.audio_engine import AudioEngine
from core.playback import PlaybackEngine


# Map of soundfont-name → filesystem path. The name on the LEFT is what
# playback.py's INSTRUMENT_SOURCES will reference. The path on the RIGHT
# is what's actually on disk. DEFAULT_SOUNDFONT in playback.py must be one
# of these names ("compifont" by default).
SOUNDFONTS: dict[str, str] = {
    "compifont":      "soundfonts/Compifont.sf2",
    "musyng":         "soundfonts/Musyng_Kite.sf2",
    "tyroland":       "soundfonts/TyrolandGS27fixed.sf2",
    "timbres":        "soundfonts/Timbres_of_Heaven_(XGM)_4.00(G).sf2",
    "hq_orch":        "soundfonts/HQ_Orchestral_Soundfont_Collection.sf2",
    "fluidr3":        "soundfonts/FluidR3_GM_GS.sf2",
    "musescore":      "soundfonts/MuseScore_General.sf2",
    "guitar_metal":   "soundfonts/Guitar_for_Metal_GM.sf2",
    "drums_hardrock": "soundfonts/Drums_HardRockDrumsV3.sf2",
}

# Which soundfont is loaded first (registered as the engine's default).
# Must match playback.DEFAULT_SOUNDFONT or sounds won't route correctly.
PRIMARY_SF = "compifont"


def main():
    audio = AudioEngine()

    primary_path = SOUNDFONTS[PRIMARY_SF]
    if not audio.initialize(primary_path, soundfont_name=PRIMARY_SF):
        print(f"Audio failed to initialize with '{PRIMARY_SF}' at {primary_path}.")
        return
    print(f"Loaded primary soundfont: {PRIMARY_SF} ({primary_path})")

    # Load all the others. load_soundfont() prints its own warnings on miss/failure;
    # missing files are non-fatal — playback just falls back to the primary.
    for name, path in SOUNDFONTS.items():
        if name == PRIMARY_SF:
            continue
        if audio.load_soundfont(name, path):
            print(f"Loaded soundfont: {name} ({path})")

    playback = PlaybackEngine(audio)

    tests = [
        ("Generic backing — Am Dm E7 Am",
            ['Am', 'Dm', 'E7', 'Am'], "generic", 100),
        ("Neoclassical metal — Am G F E (Andalusian)",
            ['Am', 'G', 'F', 'E'], "neoclassical_metal", 110),
        ("Jens organ — Am Dm E7 Am",
            ['Am', 'Dm', 'E7', 'Am'], "jens_organ", 90),
        ("Bach toccata — D minor descent",
            ['Dm', 'C', 'Bb', 'A'], "bach_toccata", 80),
        ("Jazz ii-V-I — Dm7 G7 Cmaj7",
            ['Dm7', 'G7', 'Cmaj7'], "jazz", 120),
        ("Blues in A — A7 D7 A7 E7",
            ['A7', 'D7', 'A7', 'E7'], "blues", 100),
    ]

    for label, syms, style, tempo in tests:
        print(f"\n>>> {label} (style={style}, tempo={tempo})")
        prog = ChordProgression.parse(syms)
        playback.play_progression(prog, tempo=tempo, style=style, loop=False)
        # Wait for it to finish (4 chords × 1 bar × seconds-per-bar)
        bars = len(syms)
        seconds = bars * (60.0 / tempo) * 4
        time.sleep(seconds + 0.5)
        playback.stop()
        time.sleep(0.5)  # short pause between examples

    print("\n>>> Looping demo: Am G F E in neoclassical_metal at 110bpm")
    print(">>> (loops until you press Enter)")
    prog = ChordProgression.parse(['Am', 'G', 'F', 'E'])
    playback.play_progression(prog, tempo=110, style="neoclassical_metal", loop=True)
    input()
    playback.stop()
    audio.shutdown()


if __name__ == "__main__":
    main()