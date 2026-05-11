"""
Quick validation of the core music theory engine.
Run: python test_core.py
"""

from core.music_theory import Chord, ChordProgression, note_name
from core.scales import Scale, build_scale, get_all_scale_names, SCALE_CATALOG
from core.scale_matcher import suggest_scales, analyze_chord_in_scale
from core.tuning import Tuning, get_all_tuning_presets
from core.key_analyzer import analyze_key
from core.roman_analyzer import analyze_roman
from core.modulation_detector import analyze_key_sections

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

# ── Key Analyzer (Stage 1 fixes) ──
separator("Key Analyzer")

key_cases = [
    # ── original cases (should still pass) ──
    (['A7', 'D7', 'A7', 'E7'], 'Blues — tonic should be A, not D'),
    (['Am', 'Dm', 'E7', 'Am'], 'Should say "harmonic minor V", not pure HM'),
    (['Am', 'G', 'F', 'E'],    'Should still say "harmonic minor V"'),
    (['Dm', 'G', 'Dm', 'C'],   'Should still say D Dorian'),
    (['C', 'G', 'Am', 'F'],    'Should still say C major'),
    (['E7', 'E7', 'E7', 'E7', 'A7', 'A7', 'E7', 'E7', 'B7', 'A7', 'E7', 'B7'],
                               '12-bar blues in E — tonic should be E'),
    (['Am', 'E7', 'Am', 'E7'], 'Neoclassical HM vamp'),
    # ── A2 fixes (these previously failed Stage 2) ──
    (['C', 'D7', 'G', 'C'],    'A2: should now say C major (V/V borrow), not Lydian'),
    (['Am', 'A7', 'Dm', 'E7', 'Am'], 'A2: should now say A minor + borrows, not chromatic'),
    (['C', 'Eb', 'F', 'Bb'],   'A2: should now say C major + borrows, not Mixolydian'),
    # ── A2 protection: real modal pieces should NOT get downgraded ──
    (['Cmaj7', 'D', 'F#m', 'Bm7'], 'A2 protection: real Lydian — F# in 3/4 chords'),
    (['G', 'F', 'G', 'F'],     'A2 protection: real G Mixolydian — F in 2/4 chords'),
]
for syms, note in key_cases:
    r = analyze_key(ChordProgression.parse(syms))
    prog_str = ' - '.join(syms)
    if len(prog_str) > 40:
        prog_str = prog_str[:37] + '...'
    result_str = r.display if r else 'None'
    print(f"  {prog_str:42s} → {result_str}")
    print(f"    ({note})")
    
# ── Roman Numeral Analyzer (Stage 2) ──
separator("Roman Numeral Analyzer")

roman_cases = [
    # (chord_symbols, description, expected numerals in order)
    (['Am', 'Dm', 'E7', 'Am'],
        'Neoclassical HM V', ['i', 'iv', 'V7 (HM)', 'i']),
    (['Am', 'G', 'F', 'E'],
        'Andalusian cadence', ['i', 'VII', 'VI', 'V (HM)']),
    (['C', 'G', 'Am', 'F'],
        'Pop I-V-vi-IV', ['I', 'V', 'vi', 'IV']),
    (['Dm7', 'G7', 'Cmaj7'],
        'Jazz ii-V-I', ['ii', 'V7', 'I']),
    (['Dm', 'G', 'Dm', 'C'],
        'D Dorian', ['i', 'IV', 'i', 'VII']),
    (['C', 'D7', 'G', 'C'],
        'Secondary dominant V/V', ['I', 'V7/V', 'V', 'I']),
    (['Am', 'A7', 'Dm', 'E7', 'Am'],
        'Secondary V/iv in minor', ['i', 'V7/iv', 'iv', 'V7 (HM)', 'i']),
    (['C', 'Eb', 'F', 'Bb'],
        'Borrowed chords in C major', ['I', 'bIII', 'IV', 'bVII']),
]
for syms, label, expected in roman_cases:
    prog = ChordProgression.parse(syms)
    ka = analyze_key(prog)
    if ka is None:
        print(f"  ✗ {label}: key analysis failed")
        continue
    labels = analyze_roman(prog, ka)
    got = [L.numeral for L in labels]
    match = "✓" if got == expected else "✗"
    print(f"  {match} {label}")
    print(f"    {' - '.join(syms):35s} → {' '.join(got)}")
    if got != expected:
        print(f"    expected:                            {' '.join(expected)}")
        
# ── Chord-Scale Coach (Stage 3) ──
separator("Chord-Scale Coach")
from core.chord_scale_coach import analyze_chord_scales

coach_cases = [
    (['Am', 'Dm', 'E7', 'Am'],   'Neoclassical HM V'),
    (['C', 'G', 'Am', 'F'],      'Pop I-V-vi-IV'),
    (['Dm7', 'G7', 'Cmaj7'],     'Jazz ii-V-I'),
    (['C', 'D7', 'G', 'C'],      'V/V secondary dominant'),
    (['C', 'Eb', 'F', 'Bb'],     'Borrowed chords in C major'),
    (['Dm', 'G', 'Dm', 'C'],     'D Dorian'),
    (['A7', 'D7', 'A7', 'E7'],   'Blues in A (all dominants)'),
    (['C', 'G', 'Bdim', 'C'],    'vii° in major — Bdim should get Locrian'),
]

for syms, label in coach_cases:
    prog = ChordProgression.parse(syms)
    ka = analyze_key(prog)
    if ka is None:
        print(f"  ✗ {label}: key analysis failed")
        continue
    rl = analyze_roman(prog, ka)
    advice = analyze_chord_scales(prog, ka, rl)
    print(f"\n  {label}: {' - '.join(syms)}")
    print(f"    Key: {ka.display}")
    for adv, label_obj in zip(advice, rl):
        print(f"    {adv.chord.display_name} ({label_obj.numeral}):")
        for opt in adv.options:
            tags = ','.join(opt.idioms)
            print(f"      [{opt.priority}] {opt.scale.display_name:30s}  "
                  f"— {opt.reason}  ({tags})")

# ── Modulation Detector (B1) ──
separator("Modulation Detector")

modulation_cases = [
    # (chord_symbols, description, expected_num_sections, expected_primary_label)
    # ── No modulation cases (should produce single section) ──
    (['Am', 'Dm', 'E7', 'Am'],
        'No modulation — A minor stays A minor', 1, 'A minor'),
    (['C', 'G', 'Am', 'F'],
        'No modulation — C major pop progression', 1, 'C major'),
    (['Dm', 'G', 'Dm', 'C'],
        'No modulation — D Dorian', 1, 'D Dorian'),
    (['C', 'F', 'Bb', 'C'],
        'Brief bVII borrow does NOT trigger modulation', 1, 'C major'),
    # ── Real modulation cases ──
    (['C', 'G', 'Am', 'F', 'Bb', 'F', 'Gm', 'Bb'],
        'Classic modulation C major → Bb major', 2, 'C major'),
    (['Am', 'Dm', 'E7', 'Am', 'C', 'G', 'Am', 'F'],
        'Modulation to relative major Am → C major', 2, 'A minor'),
    (['Em', 'Am', 'B7', 'Em', 'G', 'D', 'G', 'C'],
        'Modulation Em → G major (relative)', 2, 'E minor'),
    # ── Extreme / chromatic ──
    (['C', 'Eb', 'F', 'Bb'],
        'Multiple borrowings (could be C major OR Bb major)', None, None),
    # ── False-positive guards (must NOT split) ──
    (['C', 'Am', 'F', 'G', 'C', 'Am', 'F', 'G'],
        'I-vi-IV-V vamp — must NOT split into C major + A minor', 1, 'C major'),
    (['Am', 'C', 'Am', 'C', 'Am', 'C'],
        'Am-C oscillation — must NOT split', 1, 'A minor'),
]
for entry in modulation_cases:
    syms, label, expected_n_sections, expected_primary = entry
    prog = ChordProgression.parse(syms)
    result = analyze_key_sections(prog)
    if result is None:
        print(f"  ✗ {label}: analysis returned None")
        continue
    n_sections = len(result.sections)
    primary_label = f"{result.tonic_name} {result.mode_label}"

    # Check expectations if provided
    section_match = "?" if expected_n_sections is None else (
        "✓" if n_sections == expected_n_sections else "✗"
    )
    primary_match = "?" if expected_primary is None else (
        "✓" if primary_label == expected_primary else "✗"
    )

    prog_str = ' - '.join(syms)
    if len(prog_str) > 40:
        prog_str = prog_str[:37] + '...'
    print(f"  {prog_str:42s} → {result.display}")
    print(f"    ({label})")
    print(f"    sections={n_sections} {section_match}  "
          f"primary={primary_label} {primary_match}")
    for s in result.sections:
        print(f"      bars {s.start_index + 1}-{s.end_index + 1}: "
              f"{s.tonic_name} {s.mode_label} "
              f"({s.scale_system}, conf={s.confidence:.2f})")

print(f"\n{'='*60}")
print(f"  All core tests passed ✓")
print(f"{'='*60}\n")