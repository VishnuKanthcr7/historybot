// Accepted spelling/name variants for fill-in-the-blank answers. Deliberately a short, curated list: each group
// names ONE person/term, so a variant can never turn a wrong person into a right answer. Matching is done on
// normalized text (lower case, accents and punctuation removed) and also with spaces removed, so
// "Din-e-Ilahi", "din e ilahi" and "dineilahi" compare equal.
export const NAME_GROUPS = [
  ["babur", "babar", "zahir ud din muhammad babur", "zahiruddin muhammad babur", "zahir ud din babur", "zahiruddin babur"],
  ["humayun", "nasir ud din muhammad humayun", "nasiruddin muhammad humayun", "nasiruddin humayun"],
  ["akbar", "jalal ud din muhammad akbar", "jalaluddin muhammad akbar", "jalaluddin akbar", "akbar the great"],
  ["jahangir", "nur ud din muhammad salim", "nuruddin muhammad salim", "salim"],
  ["shah jahan", "shahjahan", "khurram", "prince khurram", "shihab ud din muhammad khurram"],
  ["aurangzeb", "aurangzib", "alamgir", "aurangzeb alamgir", "muhi ud din muhammad aurangzeb", "muhiuddin muhammad aurangzeb"],
  ["sher shah", "shershah", "sher shah suri", "farid khan", "farid"],
  ["shivaji", "chhatrapati shivaji", "shivaji maharaj", "chhatrapati shivaji maharaj", "shivaji bhonsle"],
  ["jijabai", "jija bai", "jijau", "rajmata jijabai"],
  ["sukaphaa", "sukapha", "chaolung sukaphaa", "siu ka pha"],
  ["din e ilahi", "din i ilahi", "deen e ilahi", "din ilahi", "tauhid i ilahi"],
  ["turkish", "turki", "chagatai turkish", "chagatai"],
];

export const compact = (s) => String(s || "").replace(/\s+/g, "");

const groupOf = new Map();
for (const group of NAME_GROUPS) for (const v of group) groupOf.set(compact(v), group);

// Returns the set of compact forms that count as correct for the accepted (already normalized) answers.
export function expandAccepted(normalizedAnswers) {
  const out = new Set();
  for (const a of normalizedAnswers) {
    out.add(compact(a));
    const g = groupOf.get(compact(a));
    if (g) for (const v of g) out.add(compact(v));
  }
  return out;
}
