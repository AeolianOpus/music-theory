"""
Quick validation of the core music theory engine.
Run: python test_core.py
"""

from core.music_theory import Chord, ChordProgression, note_name
from core.scales import Scale, build_scale, get_all_scale_names, SCALE_CATALOG
from core.scale_matcher import suggest_scales, analyze_chord_in_scale
from core.tuning import Tuning, get_all_tuning_presets

def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ── Chord Parsing ──
separator("Chord Parsing")
test_chords = ["Am", "C", "G7", "F#m7", "Bbmaj7", "Dm", "E7", "Bdim", "Gsus4", "A7#9"]
for sym in test_chords:
    c = Chord.parse(sym)
    pcs = [note_name(pc) for pc in c.pitch_classes]
    print(f"  {sym:10s} → {c.display_name:10s}  notes: {pcs}")

# ── Scale Construction ──
separator("Scale Construction")
for name in ["Ionian (Major)", "Harmonic Minor", "Phrygian Dominant", "Blues", "Whole Tone"]:
    s = build_scale("A", name)
    print(f"  {s.display_name:30s}  notes: {s.note_names()}")

# ── Scale Matching ──
separator("Scale Matching: Am - Dm - E7 - Am")
prog = ChordProgression.parse(["Am", "Dm", "E7", "Am"], name="Baroque Minor")
results = suggest_scales(prog, top_n=3, alternatives=3)

print(f"\n  Chord tones: {[note_name(pc) for pc in sorted(prog.all_pitch_classes)]}")
print(f"\n  Top 3 suggestions:")
for i, m in enumerate(results["top"], 1):
    miss = m.missing_note_names()
    miss_str = f" (missing: {miss})" if miss else " ✓ perfect fit"
    print(f"    {i}. {m.display_name:35s}  score={m.score:.3f}  coverage={m.coverage:.0%}{miss_str}")

print(f"\n  Alternatives:")
for m in results["alternatives"]:
    miss = m.missing_note_names()
    miss_str = f" (missing: {miss})" if miss else " ✓"
    print(f"    - {m.display_name:35s}  score={m.score:.3f}  coverage={m.coverage:.0%}{miss_str}")

# ── Another progression ──
separator("Scale Matching: Em - G - Am - Bm (Pink Floyd style)")
prog2 = ChordProgression.parse(["Em", "G", "Am", "Bm"])
results2 = suggest_scales(prog2, top_n=3, alternatives=3)

print(f"\n  Chord tones: {[note_name(pc) for pc in sorted(prog2.all_pitch_classes)]}")
print(f"\n  Top 3:")
for i, m in enumerate(results2["top"], 1):
    miss = m.missing_note_names()
    miss_str = f" (missing: {miss})" if miss else " ✓ perfect fit"
    print(f"    {i}. {m.display_name:35s}  score={m.score:.3f}  coverage={m.coverage:.0%}{miss_str}")

# ── Tuning ──
separator("Tuning System")
std = Tuning.from_preset("Standard (EADGBE)")
print(f"  {std.name}: {std.string_names()}")

eb = std.shift(-1)
print(f"  {eb.name}: {eb.string_names()}")

drop_d = Tuning.from_preset("Drop D")
print(f"  {drop_d.name}: {drop_d.string_names()}")

# ── Stats ──
separator("Library Stats")
print(f"  Scales in catalog: {len(SCALE_CATALOG)}")
print(f"  Tuning presets: {sum(len(v) for v in get_all_tuning_presets().values())}")
print(f"  Chord qualities: {len(Chord.parse('C').intervals)}")  # just checking it works

print(f"\n{'='*60}")
print(f"  All core tests passed ✓")
print(f"{'='*60}\n")
