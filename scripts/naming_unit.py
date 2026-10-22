import sys; sys.path.insert(0, ".")
from rag.engine.naming import full_name, apply
cases = [
 ("Shivaji founded the Maratha kingdom.", "Chhatrapati Shivaji Maharaj founded the Maratha kingdom."),
 ("Shivaji's guru was Ramdas.", "Chhatrapati Shivaji Maharaj's guru was Ramdas."),
 ("Chhatrapati Shivaji Maharaj was brave.", "Chhatrapati Shivaji Maharaj was brave."),
 ("Shivaji Maharaj ruled.", "Shivaji Maharaj ruled."),
 ("He was called Shivaji II.", "He was called Shivaji II."),
 ('The textbook says "Shivaji was born in 1627".', 'The textbook says "Shivaji was born in 1627".'),
 ("Shivajinagar is a place.", "Shivajinagar is a place."),
 ("Akbar and Shivaji.", "Akbar and Chhatrapati Shivaji Maharaj."),
]
bad = 0
for a, b in cases:
    got = full_name(a)
    if got != b: bad += 1; print("FAIL", repr(a), "->", repr(got))
d = apply({"title": "Shivaji", "sections": [{"text": "Shivaji won."}], "sources": [{"excerpt": "Shivaji won."}], "excerpt": "Shivaji"})
assert d["title"] == "Chhatrapati Shivaji Maharaj" and d["sections"][0]["text"].startswith("Chhatrapati") and d["sources"][0]["excerpt"] == "Shivaji won." and d["excerpt"] == "Shivaji", d
print(f"naming_unit {len(cases)+1-bad}/{len(cases)+1}")
sys.exit(1 if bad else 0)
