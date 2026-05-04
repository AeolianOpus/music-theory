from core.music_theory import ChordProgression
from core.key_analyzer import analyze_key

for syms in [['C','D7','G','C'], ['Am','A7','Dm','E7','Am'], ['C','Eb','F','Bb']]:
    r = analyze_key(ChordProgression.parse(syms))
    print(' - '.join(syms), '->', r.display if r else 'None')