"""
Manual playback test. Run from project root: python test_playback.py
Plays a few progressions across different style presets.
Press Ctrl+C to stop early.
"""
import time
from core.music_theory import ChordProgression
from core.audio_engine import AudioEngine
from core.playback import PlaybackEngine


SOUNDFONT_PATH = "soundfonts/FluidR3_GM.sf2"  # adjust to your actual SF2 file


def main():
    audio = AudioEngine()
    if not audio.initialize(SOUNDFONT_PATH):
        print("Audio failed to initialize. Check SoundFont path.")
        return

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